"""
J.A.R.V.I.S. Phone Link
=======================
Lets you talk to J.A.R.V.I.S. from your phone while both are on the same
Wi-Fi. A tiny local web server (Flask) serves a mobile chat page; the
desktop HUD shows a QR code you scan to jump straight to it.

    Phone (browser)  <--Wi-Fi-->  PC: Flask on 0.0.0.0:<port>
                       GET  /            -> mobile chat page
                       POST /api/chat    -> streamed AI / command reply
                       GET  /api/status  -> link status

The page is served over HTTPS with a self-signed certificate (generated
once, cached next to this file) — browsers require HTTPS before they let
web pages use the microphone, which is what powers voice input on the
phone. The phone shows a one-time "not private" warning for the
self-signed cert; tapping through is safe on your own network.

No cloud, no accounts: everything stays on your home network. The AI
still runs on your PC (Ollama), but requests sent from the phone reply
only on the phone — the desktop stays quiet.

Run it from the GUI — a "PHONE LINK" button in the HUD starts the server
and shows the QR code. This module can also be used standalone:

    from services.phone_link import PhoneLinkServer
    server = PhoneLinkServer(assistant)   # assistant = PersonalizedAssistant
    server.start()
    print(server.url)
"""

import datetime
import io
import ipaddress
import os
import socket
import threading

from decouple import config

from core.ollama import BIG_MODEL, split_deep_marker
from functions.online_ops import (
    have_internet, play_on_youtube, search_on_wikipedia,
)
from functions.os_ops import looks_like_command

try:
    from services.ollama_manager import ensure_ollama, is_online
except Exception:  # pragma: no cover - only used when streaming chat
    def is_online():
        return True

    def ensure_ollama(timeout=30, on_status=None):
        return True

try:
    from flask import Flask, Response, request, stream_with_context
except Exception:
    Flask = None

try:
    import qrcode
except Exception:
    qrcode = None

try:
    import psutil
except Exception:
    psutil = None

PORT_DEFAULT = 5080


# ---------------------------------------------------------------------------
# LAN helpers
# ---------------------------------------------------------------------------
def _is_private(ip):
    """True for typical home-network IPv4 addresses (RFC1918 + CGNAT)."""
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return (a == 10
            or (a == 172 and 16 <= b <= 31)
            or (a == 192 and b == 168)
            or (a == 100 and 64 <= b <= 127))


def get_lan_ip():
    """Best-guess LAN IP for this machine — the address a phone on the same
    Wi-Fi can reach. Tries the default-route interface first (a UDP connect
    sends no packets, so it works offline too), then any private adapter
    via psutil, then hostname resolution."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and _is_private(ip):
                return ip
        finally:
            s.close()
    except Exception:
        pass
    if psutil is not None:
        try:
            for _name, addrs in psutil.net_if_addrs().items():
                for a in addrs:
                    if a.family == socket.AF_INET and _is_private(a.address):
                        return a.address
        except Exception:
            pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


# Cert files stay at the project root (covered by .gitignore) so they
# survive code moves and are never regenerated unnecessarily.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CERT_FILE = os.path.join(_PROJECT_ROOT, "phone_link_cert.pem")
_KEY_FILE = os.path.join(_PROJECT_ROOT, "phone_link_key.pem")


def _cert_contains_ip(cert_path, ip):
    """True when the cached cert's Subject Alternative Names include the
    given IP (browsers reject HTTPS when the IP isn't in the SANs)."""
    try:
        from cryptography import x509
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value
        wanted = ipaddress.ip_address(ip)
        return any(wanted == entry
                   for entry in san.get_values_for_type(x509.IPAddress))
    except Exception:
        return False


def ensure_ssl_context():
    """Return (cert_pem_path, key_pem_path) for a cached self-signed cert
    (regenerated when the LAN IP changes), or None when the cryptography
    package is missing. HTTPS is what lets the phone browser use its mic."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except Exception as e:
        print(f"[phone] HTTPS unavailable ({e}) — chat still works over "
              "HTTP, but voice input from the phone needs it. "
              "Run: pip install cryptography")
        return None

    ip = get_lan_ip()
    if (os.path.exists(_CERT_FILE) and os.path.exists(_KEY_FILE)
            and _cert_contains_ip(_CERT_FILE, ip)):
        return (_CERT_FILE, _KEY_FILE)

    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "J.A.R.V.I.S. Phone Link"),
        ])
        san_entries = []
        for addr in {ip, "127.0.0.1"}:
            try:
                san_entries.append(x509.IPAddress(ipaddress.ip_address(addr)))
            except ValueError:
                pass
        san_entries.append(x509.DNSName("localhost"))
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(san_entries),
                           critical=False)
            .sign(key, hashes.SHA256())
        )
        with open(_KEY_FILE, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption()))
        with open(_CERT_FILE, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        print(f"[phone] generated self-signed HTTPS cert for {ip}")
        return (_CERT_FILE, _KEY_FILE)
    except Exception as e:
        print(f"[phone] could not generate HTTPS cert: {e}")
        return None


def get_phone_url(port=None, ip=None, https=True):
    """The URL a phone on the same network should open. HTTPS by default —
    that's what the phone link serves (needed for voice input)."""
    scheme = "https" if https else "http"
    return f"{scheme}://{ip or get_lan_ip()}:{int(port or PORT_DEFAULT)}"


def make_qr_png(data, box_size=10, border=2):
    """Return PNG bytes for a scannable QR code, or None when the qrcode
    library (or Pillow) is missing. Black-on-white for maximum scanner
    compatibility."""
    if qrcode is None:
        return None
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"[phone] QR generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# The web server
# ---------------------------------------------------------------------------
class PhoneLinkServer:
    """Exposes J.A.R.V.I.S. to phones on the same network. Runs in a daemon
    thread; start()/stop() are safe to call from the GUI thread."""

    def __init__(self, assistant, port=None):
        self.assistant = assistant
        self.port = int(port or config("PHONE_PORT", default=PORT_DEFAULT))
        self.followups = {}          # session id -> pending follow-up kind
        self._thread = None
        self._httpd = None
        self._running = False
        # Serializes phone requests so the busy check and the tts.speak
        # wrapper swap below are exclusive (Flask runs threaded=True).
        self._process_lock = threading.Lock()
        # HTTPS (self-signed cert) is required for the phone browser's
        # microphone; falls back to plain HTTP for chat-only when the
        # cryptography package is missing.
        self.ssl_context = ensure_ssl_context()
        self.ssl_enabled = self.ssl_context is not None
        self.app = self._build_app()

    # -- public API ---------------------------------------------------------
    @property
    def url(self):
        return get_phone_url(self.port, https=self.ssl_enabled)

    @property
    def is_running(self):
        return self._running

    def start(self):
        if self._running:
            return True
        # Probe the port first so a busy port is reported synchronously
        # instead of failing silently in the background thread.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(("0.0.0.0", self.port))
            finally:
                s.close()
        except OSError as e:
            print(f"[phone] port {self.port} is busy: {e}")
            return False
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        httpd = self._httpd
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception as e:
                print(f"[phone] shutdown error: {e}")

    # -- server internals ---------------------------------------------------
    def _run(self):
        if Flask is None:
            print("[phone] Flask is not installed — phone link disabled. "
                  "Run: pip install flask")
            self._running = False
            return
        try:
            import logging
            logging.getLogger("werkzeug").setLevel(logging.ERROR)
            from werkzeug.serving import make_server
            if not self._running:
                return
            self._httpd = make_server("0.0.0.0", self.port, self.app,
                                     threaded=True,
                                     ssl_context=self.ssl_context)
            proto = "HTTPS" if self.ssl_enabled else "HTTP"
            print(f"[phone] J.A.R.V.I.S. phone link running at {self.url} "
                  f"({proto}, phone must be on the same Wi-Fi)")
            self._httpd.serve_forever()
        except Exception as e:
            print(f"[phone] server error: {e}")
        finally:
            self._running = False

    def _build_app(self):
        app = Flask("phone_link")
        server = self

        @app.route("/")
        def index():
            return _INDEX_HTML

        @app.route("/api/status")
        def status():
            a = server.assistant
            return {
                "ok": True,
                "botname": a.botname,
                "model": a.model,
                "busy": bool(a.is_processing),
            }

        @app.route("/api/chat", methods=["POST"])
        def chat():
            data = request.get_json(silent=True) or {}
            message = (data.get("message") or "").strip()
            session = str(data.get("session") or "default")
            if not message:
                return Response("Say something — I can't read minds yet!",
                                mimetype="text/plain; charset=utf-8")
            gen = server._chat_stream(message, session)
            return Response(stream_with_context(gen),
                            mimetype="text/plain; charset=utf-8")

        return app

    # -- the chat handler ----------------------------------------------------
    def _chat_stream(self, message, session):
        """Handle one phone message, yielding reply text (streamed for AI
        chat, single chunk for commands). Mirrors the desktop HUD's worker
        flow (commands, follow-ups, AI streaming) — except the reply is
        delivered to the phone only, never spoken on the desktop.

        The whole request runs under ``self._process_lock``: the busy check
        is shared with the desktop HUD worker (same ``is_processing`` flag),
        and the ``tts.speak`` wrapper swap below must be exclusive — two
        overlapping requests could otherwise leak a stale wrapper onto
        ``assistant.tts.speak``."""
        assistant = self.assistant
        msg = (message or "").strip()
        if not msg:
            yield "Say something — I can't read minds yet!"
            return

        with self._process_lock:
            if assistant.is_processing:
                yield "One sec — I'm still finishing the previous request."
                return
            assistant.is_processing = True
            try:
                msg, deep = split_deep_marker(msg)
                lowered = msg.lower()

                # -- answer a pending wikipedia / youtube follow-up ---------
                kind = self.followups.pop(session, "") if session else ""
                if kind:
                    assistant.history.append(f"User: {msg}")
                    if not have_internet():
                        what = ("look things up on Wikipedia"
                                if kind == "wikipedia"
                                else "play YouTube videos")
                        yield (f"You're offline right now, so I can't {what}. "
                               "I can still chat and run local commands.")
                        return
                    if kind == "wikipedia":
                        try:
                            results = search_on_wikipedia(msg)
                            short = results[:200] + ("..."
                                                     if len(results) > 200
                                                     else "")
                            text = f"Wikipedia says: {short}"
                        except Exception:
                            text = "Wikipedia's not playing nice right now."
                    else:
                        play_on_youtube(msg)
                        text = f"Playing {msg} on YouTube — enjoy!"
                    assistant.history.append(f"AI: {text}")
                    yield text
                    return

                # -- farewell: never let handle_command's exit(0) kill the app
                if "bye" in lowered or "goodbye" in lowered:
                    text = f"See ya, {assistant.username}! Ping me anytime!"
                    assistant.history.append(f"User: {msg}")
                    assistant.history.append(f"AI: {text}")
                    threading.Thread(
                        target=assistant.summarize_and_save_history,
                        daemon=True).start()
                    yield text
                    return

                # -- follow-up prompts (same flow as the desktop HUD) --------
                if not looks_like_command(lowered):
                    if "wikipedia" in lowered:
                        self.followups[session] = "wikipedia"
                        yield "What should I look up on Wikipedia, friend?"
                        return
                    if "youtube" in lowered:
                        self.followups[session] = "youtube"
                        yield "What do you want to jam to on YouTube?"
                        return

                # Capture everything the assistant "speaks" so command
                # replies come back as real text (any TTS engine) — without
                # forwarding it to the desktop speaker: a phone request
                # replies on the phone only.
                old_speak = assistant.tts.speak
                captured = []

                def _collect(text):
                    captured.append(text)

                assistant.tts.speak = _collect
                try:
                    # -- local / online commands -----------------------------
                    try:
                        handled = assistant.handle_command(lowered)
                    except Exception as e:
                        print(f"[phone] command error: {e}")
                        handled = False
                    if handled:
                        yield " ".join(captured).strip() or "Done!"
                        return

                    # -- normal AI chat: stream from the local model ---------
                    if not is_online():
                        ensure_ollama(timeout=30)
                    old_model = assistant.ollama.model
                    swapped = deep and old_model != BIG_MODEL
                    if swapped:
                        assistant.ollama.model = BIG_MODEL
                    try:
                        parts = []
                        # speak=False keeps the desktop silent — the phone
                        # browser streams the reply itself.
                        gen = assistant.generate_reply(msg, speak=False,
                                                       paced=False)
                        first = True
                        for token in gen:
                            if first:
                                # forward any pre-reply announcements (e.g.
                                # the "give me a sec" web-search notice) so
                                # the phone sees the same feedback the HUD
                                # would show
                                first = False
                                notice = " ".join(captured).strip()
                                if notice:
                                    yield notice + "\n"
                            parts.append(token)
                            yield token
                        reply = "".join(parts).strip()
                    finally:
                        # resync to the model currently selected in the HUD
                        assistant.ollama.model = assistant.model
                    if reply:
                        assistant.history.append(f"User: {msg}")
                        assistant.history.append(f"AI: {reply}")
                finally:
                    assistant.tts.speak = old_speak
            except Exception as e:
                print(f"[phone] handler error: {e}")
                yield "Yikes, something went wrong on my end."
            finally:
                assistant.is_processing = False


# ---------------------------------------------------------------------------
# Mobile chat page (self-contained; no templates directory needed)
# ---------------------------------------------------------------------------
_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#00060a">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>J.A.R.V.I.S. — Phone Link</title>
<style>
:root{
  --bg:#00060a; --panel:#010d14; --panel2:#02222f; --border:#0d3347;
  --border-b:#1a5c7a; --pri:#00d4ff; --acc:#ff6b00; --green:#00ff88;
  --red:#ff3355; --text:#8ffcff; --dim:#3a8a9a; --white:#d8f8ff;
}
*{box-sizing:border-box; margin:0; padding:0; -webkit-tap-highlight-color:transparent;}
html,body{height:100%;}
body{
  background:
    radial-gradient(1100px 520px at 50% -8%, #021320 0%, transparent 60%),
    var(--bg);
  color:var(--text);
  font-family:system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  display:flex; flex-direction:column;
  padding:env(safe-area-inset-top) env(safe-area-inset-right) 0 env(safe-area-inset-left);
}
header{
  display:flex; align-items:center; gap:8px; padding:11px 14px;
  border-bottom:1px solid var(--border);
  background:linear-gradient(180deg, rgba(0,212,255,.06), transparent);
}
.logo{font-family:"Courier New", monospace; font-weight:700; font-size:16px;
  color:var(--pri); letter-spacing:1px;
  text-shadow:0 0 14px rgba(0,212,255,.55);}
.sub{font-family:"Courier New", monospace; font-size:8px; color:var(--dim);
  letter-spacing:1px;}
.status{margin-left:auto; display:flex; align-items:center; gap:6px;
  font-family:"Courier New", monospace; font-size:9px; color:var(--dim);}
#dot{width:8px; height:8px; border-radius:50%; background:var(--red);
  box-shadow:0 0 8px var(--red);}
#dot.on{background:var(--green); box-shadow:0 0 8px var(--green);}
.chips{display:flex; gap:6px; padding:9px 12px; overflow-x:auto; flex-shrink:0;
  border-bottom:1px solid var(--border); scrollbar-width:none;}
.chips::-webkit-scrollbar{display:none;}
.chips button{
  flex:0 0 auto; background:var(--panel); color:var(--text);
  border:1px solid var(--border-b); border-radius:14px; padding:7px 13px;
  font-size:12.5px; cursor:pointer; white-space:nowrap; transition:all .15s;
}
.chips button:active{background:var(--pri); color:#00131b; border-color:var(--pri);}
main{flex:1; overflow-y:auto; padding:14px 12px 8px; display:flex;
  flex-direction:column; gap:10px;}
.msg{display:flex; flex-direction:column; max-width:86%;}
.msg.you{align-self:flex-end; align-items:flex-end;}
.lbl{font-family:"Courier New", monospace; font-size:8px; letter-spacing:1px;
  color:var(--dim); margin-bottom:3px;}
.msg.you .lbl{color:var(--acc);}
.body{background:var(--panel); border:1px solid var(--border);
  border-radius:12px 12px 12px 2px; padding:9px 12px; font-size:14.5px;
  line-height:1.45; color:var(--white); word-break:break-word;
  white-space:pre-wrap; box-shadow:0 2px 14px rgba(0,0,0,.35);}
.msg.you .body{background:var(--panel2); border-color:var(--border-b);
  border-radius:12px 12px 2px 12px;}
.msg.ai .body.typing{color:var(--acc); animation:pulse 1.1s ease-in-out infinite;}
@keyframes pulse{50%{opacity:.45;}}
.msg.ai .body.streaming::after{content:"\\258D"; color:var(--pri);
  animation:blink .9s steps(1) infinite;}
@keyframes blink{50%{opacity:0;}}
footer{display:flex; gap:8px; padding:10px 12px calc(10px + env(safe-area-inset-bottom));
  border-top:1px solid var(--border); background:rgba(1,13,20,.92);
  backdrop-filter:blur(6px);}
footer input{flex:1; background:var(--panel); color:var(--text);
  border:1px solid var(--border-b); border-radius:20px; padding:11px 16px;
  font-size:15px; outline:none; min-width:0;}
footer input:focus{border-color:var(--pri); box-shadow:0 0 0 2px rgba(0,212,255,.18);}
footer input::placeholder{color:var(--dim);}
footer button{width:46px; height:46px; border-radius:50%; flex:0 0 auto;
  border:1px solid var(--border-b); background:var(--panel); color:var(--pri);
  font-size:16px; cursor:pointer; display:flex; align-items:center;
  justify-content:center; transition:all .15s;}
footer button.off{opacity:.45;}
footer button:disabled{opacity:.4;}
footer button:active{background:var(--pri); color:#00131b;}
footer #mic.live{background:var(--red); color:#fff; border-color:var(--red);
  box-shadow:0 0 16px rgba(255,51,85,.65); animation:pulse 1s ease-in-out infinite;}
footer #send{background:var(--pri); color:#00131b; border:none; font-size:17px;
  box-shadow:0 0 14px rgba(0,212,255,.4);}
footer #send:disabled{opacity:.5;}
#toast{position:fixed; left:12px; right:12px; z-index:5;
  bottom:calc(78px + env(safe-area-inset-bottom));
  background:var(--panel2); border:1px solid var(--border-b); color:var(--white);
  border-radius:10px; padding:9px 12px; font-size:12.5px; line-height:1.4;
  text-align:center; opacity:0; transform:translateY(6px);
  transition:opacity .2s, transform .2s; pointer-events:none;
  box-shadow:0 4px 18px rgba(0,0,0,.45);}
#toast.show{opacity:1; transform:none;}
</style>
</head>
<body>
<header>
  <div class="logo">&#9670; J.A.R.V.I.S.</div>
  <div class="sub">LINKED TO DESKTOP HUD</div>
  <div class="status"><span id="dot"></span><span id="stxt">CONNECTING</span></div>
</header>
<div class="chips" id="chips">
  <button data-cmd="weather">&#9925; Weather</button>
  <button data-cmd="joke">&#128514; Joke</button>
  <button data-cmd="news">&#128250; News</button>
  <button data-cmd="my ip">&#127760; My IP</button>
  <button data-cmd="screenshot">&#128248; Screenshot</button>
  <button data-cmd="open notepad">&#128209; Notepad</button>
</div>
<main id="log"></main>
<div id="toast"></div>
<footer>
  <button id="tts" title="Read replies aloud on this phone">&#128266;</button>
  <button id="mic" title="Talk to J.A.R.V.I.S." aria-label="Voice input">&#127908;</button>
  <input id="inp" placeholder="Ask J.A.R.V.I.S..." autocomplete="off"
         autocapitalize="sentences" enterkeyhint="send">
  <button id="send" title="Send">&#10148;</button>
</footer>
<script>
var $ = function(id){ return document.getElementById(id); };
var sid = localStorage.getItem('jid') || ('p' + Math.random().toString(36).slice(2) + Date.now().toString(36));
localStorage.setItem('jid', sid);
var log = $('log'), inp = $('inp');
var streaming = false, ttsOn = true;

var toastTimer = null;
function flash(msg){
  var t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function(){ t.classList.remove('show'); }, 3500);
}

function scrollDown(){ log.scrollTop = log.scrollHeight; }

function addMsg(who, text){
  var row = document.createElement('div');
  row.className = 'msg ' + who;
  var lbl = document.createElement('div');
  lbl.className = 'lbl';
  lbl.textContent = who === 'you' ? 'YOU' : 'J.A.R.V.I.S.';
  var body = document.createElement('div');
  body.className = 'body';
  body.textContent = text || '';
  row.appendChild(lbl);
  row.appendChild(body);
  log.appendChild(row);
  scrollDown();
  return body;
}

function speak(text){
  if(!ttsOn || !('speechSynthesis' in window)) return;
  try{
    speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(text.replace(/[\\u25C8\\u25C7\\u25CD\\u2014\\u2026]/g, ' '));
    u.rate = 1; u.pitch = 1;
    speechSynthesis.speak(u);
  }catch(e){}
}

// -- voice input: browser Web Speech API (needs HTTPS, which the phone
//    link serves via its self-signed certificate) -----------------------
var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
var rec = null, listening = false, recCancelled = false;

function updateMic(){
  $('mic').classList.toggle('live', listening);
  $('mic').title = listening ? 'Stop listening' : 'Talk to J.A.R.V.I.S.';
}

function stopMic(){
  listening = false;
  recCancelled = true;
  updateMic();
  if(rec){ try{ rec.abort(); }catch(e){} }
}

function toggleMic(){
  if(listening){ stopMic(); return; }
  if(!SR){
    flash('Voice input needs a browser with speech support — try Chrome on Android or Safari (iOS 14.5+).');
    return;
  }
  if(!window.isSecureContext){
    flash('Your browser blocks the mic over plain HTTP — open this page via HTTPS (scan the QR again).');
    return;
  }
  rec = new SR();
  recCancelled = false;
  rec.lang = 'en-US';
  rec.interimResults = true;
  rec.maxAlternatives = 1;
  rec.continuous = false;
  rec.onstart = function(){ listening = true; updateMic(); };
  rec.onresult = function(e){
    var interim = '', final = '';
    for(var i = e.resultIndex; i < e.results.length; i++){
      var alt = e.results[i][0].transcript;
      if(e.results[i].isFinal) final += alt; else interim += alt;
    }
    if(final) inp.value = final;
    else if(interim) inp.value = interim;
  };
  rec.onend = function(){
    var text = (inp.value || '').trim();
    listening = false;
    updateMic();
    rec = null;
    var cancelled = recCancelled;
    recCancelled = false;
    if(!cancelled && text) send(text, false);
  };
  rec.onerror = function(e){
    listening = false;
    updateMic();
    rec = null;
    if(e.error === 'not-allowed' || e.error === 'service-not-allowed'){
      flash('Mic permission blocked — allow microphone access for this site in your browser.');
    } else if(e.error === 'no-speech'){
      flash('Didn\\'t catch that — tap the mic and try again.');
    } else if(e.error === 'network'){
      flash('Speech service unreachable — check your connection.');
    }
  };
  try{ rec.start(); }catch(e){ flash('Couldn\\'t start the mic.'); }
}

function send(text, keepFocus){
  // keepFocus=false from voice input — don't pop the keyboard after talking
  keepFocus = keepFocus !== false;
  text = (text || inp.value).trim();
  if(!text || streaming) return;
  inp.value = '';
  addMsg('you', text);
  var t = addMsg('ai', '');
  t.classList.add('typing');
  t.textContent = '\\u25C8 THINKING';
  streaming = true;
  $('send').disabled = true;
  $('mic').disabled = true;
  fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message: text, session: sid})
  }).then(function(res){
    if(!res.ok) throw new Error(res.status);
    return res.body.getReader();
  }).then(function(reader){
    var dec = new TextDecoder();
    t.classList.remove('typing');
    t.classList.add('streaming');
    t.textContent = '';
    function pump(){
      return reader.read().then(function(r){
        if(r.done) return;
        t.textContent += dec.decode(r.value, {stream:true});
        scrollDown();
        return pump();
      });
    }
    return pump();
  }).then(function(){
    t.classList.remove('streaming');
    var final = t.textContent.trim();
    if(final) speak(final);
  }).catch(function(){
    t.classList.remove('typing');
    t.classList.remove('streaming');
    t.textContent = 'Connection lost — is the desktop HUD still running?';
  }).finally(function(){
    streaming = false;
    $('send').disabled = false;
    $('mic').disabled = false;
    if(keepFocus) inp.focus();
  });
}

function poll(){
  fetch('/api/status').then(function(r){ return r.json(); }).then(function(j){
    $('dot').classList.add('on');
    $('stxt').textContent = j.busy ? 'THINKING' : 'ONLINE';
  }).catch(function(){
    $('dot').classList.remove('on');
    $('stxt').textContent = 'OFFLINE';
  });
}

var chips = document.querySelectorAll('#chips button');
for(var i = 0; i < chips.length; i++){
  chips[i].addEventListener('click', function(){
    send(this.getAttribute('data-cmd'));
  });
}
$('send').addEventListener('click', function(){ send(); });
$('mic').addEventListener('click', toggleMic);
inp.addEventListener('keydown', function(e){ if(e.key === 'Enter') send(); });
$('tts').addEventListener('click', function(){
  ttsOn = !ttsOn;
  $('tts').textContent = ttsOn ? '\\uD83D\\uDD0A' : '\\uD83D\\uDD07';
  $('tts').classList.toggle('off', !ttsOn);
});

addMsg('ai', 'Hey, I\\'m J.A.R.V.I.S. — linked to your desktop. Ask me anything, tap the mic to talk, or hit a quick action below!');
setInterval(poll, 10000);
poll();
</script>
</body>
</html>
"""
