#!/usr/bin/env python3
"""
Rest-Place birthday flyer - local web app.

    python3 app.py            ->  http://localhost:8000

Only two inputs change per flyer: the celebrant's photo and the name.
Background removal is optional (tick / untick "Remove background").
"""
import io, os, subprocess, sys, tempfile, threading, traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template'))
from flask import Flask, request, send_file, Response, render_template_string   # noqa: E402
from PIL import Image                                                           # noqa: E402
from render import render, CFG                                                  # noqa: E402
from imaging import load_any, UnreadableImage, describe                         # noqa: E402

app = Flask(__name__)


def _favicon() -> bytes:
    """Small orange-ring icon so the browser tab is branded (and /favicon.ico is a 200)."""
    from PIL import ImageDraw
    s = 64
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((2, 2, s - 3, s - 3), fill=(246, 146, 62, 255))
    d.ellipse((17, 17, s - 18, s - 18), outline=(255, 246, 238, 255), width=7)
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return buf.getvalue()


FAVICON = _favicon()


@app.get('/favicon.ico')
def favicon():
    return Response(FAVICON, mimetype='image/png', headers={'Cache-Control': 'public, max-age=86400'})

app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024   # room for phone HEIC / camera RAW

# Each background removal runs in its own process and needs ~1.2 GB, so only allow
# CUTOUT_SLOTS of them at a time. Extra requests wait their turn instead of OOM-ing.
CUTOUT_SLOTS = int(os.environ.get('CUTOUT_SLOTS', '1'))
_cutout_slots = threading.Semaphore(CUTOUT_SLOTS)

PAGE = r"""
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><link rel="icon" href="/favicon.ico"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rest-Place · Birthday flyer</title>
<style>
  :root{--ink:#2b2320;--muted:#8a7a72;--pink:#fdf1ea;--peach:#ff9b5a;--card:#fff;--line:#f0ddd2}
  *{box-sizing:border-box}
  body{margin:0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;color:var(--ink);
       background:radial-gradient(120% 80% at 50% 0%,#fff7f2 0%,#fdeee4 45%,#f8e2d6 100%);
       min-height:100vh;padding:28px 18px 60px}
  .wrap{max-width:1080px;margin:0 auto}
  header{text-align:center;margin-bottom:22px}
  h1{font-size:26px;margin:0 0 6px;letter-spacing:.2px}
  header p{margin:0;color:var(--muted);font-size:14px}
  .grid{display:grid;grid-template-columns:minmax(320px,420px) 1fr;gap:22px;align-items:start}
  @media (max-width:880px){.grid{grid-template-columns:1fr}}
  .card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px;
        box-shadow:0 10px 30px rgba(180,120,90,.10)}
  label{display:block;font-size:13px;font-weight:600;margin:0 0 8px}
  .drop{border:2px dashed #efcdb8;border-radius:14px;background:#fffaf7;padding:22px 16px;text-align:center;
        cursor:pointer;transition:.18s;position:relative;overflow:hidden}
  .drop.hot{border-color:var(--peach);background:#fff3ea}
  .drop input{position:absolute;inset:0;opacity:0;cursor:pointer}
  .drop strong{display:block;font-size:14px;margin-bottom:4px}
  .drop span{font-size:12px;color:var(--muted)}
  .thumb{margin-top:10px;font-size:12px;color:var(--muted);display:flex;align-items:center;gap:8px}
  .thumb img{width:44px;height:44px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}
  .badge{font-size:10px;font-weight:700;letter-spacing:.5px;color:#a2551f;background:#ffe8d6;
         border-radius:6px;padding:5px 6px}
  input[type=text]{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:12px;font-size:15px;
        font-family:inherit;background:#fffdfb}
  input[type=text]:focus{outline:2px solid #ffd9bf;border-color:#f7c4a3}
  .modes{display:grid;gap:10px}
  .mode{border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;gap:10px;
        align-items:flex-start;cursor:pointer;background:#fffdfb}
  .mode input{margin-top:3px;accent-color:#e9762f}
  .mode b{font-size:13.5px;display:block;margin-bottom:2px}
  .mode small{color:var(--muted);font-size:12px;line-height:1.35;display:block}
  .field{margin-bottom:16px}
  button{font-family:inherit;border:0;border-radius:12px;cursor:pointer;font-weight:700}
  .primary{width:100%;padding:14px;font-size:15px;color:#fff;
        background:linear-gradient(180deg,#ff9f5c,#f0762c);box-shadow:0 8px 18px rgba(240,118,44,.30)}
  .primary:disabled{filter:grayscale(.3);opacity:.7;cursor:progress}
  .ghost{padding:10px 14px;font-size:13px;background:#fff;border:1px solid var(--line);color:var(--ink)}
  .stage{min-height:420px;display:flex;align-items:center;justify-content:center;
        border-radius:14px;background:#fff8f4;border:1px solid var(--line);overflow:hidden;position:relative}
  .stage img{max-width:100%;max-height:74vh;display:block;border-radius:8px}
  .hint{color:var(--muted);font-size:13px;text-align:center;padding:40px 20px;line-height:1.5}
  .spinner{width:34px;height:34px;border-radius:50%;border:3px solid #ffd9bf;border-top-color:#f0762c;
        animation:spin .9s linear infinite;margin:0 auto 12px}
  @keyframes spin{to{transform:rotate(360deg)}}
  .actions{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
  .err{color:#b3261e;background:#fdecea;border:1px solid #f7c6c2;padding:10px 12px;border-radius:10px;
       font-size:13px;margin-top:12px;display:none}
  .foot{margin-top:18px;font-size:11.5px;color:var(--muted);text-align:center}
</style></head>
<body><div class="wrap">
  <header>
    <h1>Rest-Place Christian Centre · Birthday flyer</h1>
    <p>Upload a photo, type the name — everything else stays the same.</p>
  </header>

  <div class="grid">
    <form class="card" id="f">
      <div class="field">
        <label for="photo">Celebrant photo</label>
        <div class="drop" id="drop">
          <input type="file" id="photo" name="photo" accept="image/*,.jpg,.jpeg,.png,.heic,.heif,.avif,.webp,.tif,.tiff,.bmp,.gif,.jp2,.psd,.dng,.cr2,.cr3,.nef,.arw,.orf,.rw2,.raf" required>
          <strong>Click or drop any image here</strong>
          <span>JPG · PNG · HEIC/HEIF · AVIF · WebP · TIFF · BMP · GIF · RAW · up to 64 MB</span>
        </div>
        <div class="thumb" id="thumb" style="display:none"></div>
      </div>

      <div class="field">
        <label for="name">Name on the flyer</label>
        <input type="text" id="name" name="name" placeholder="ENTER NAME" maxlength="42" required>
      </div>

      <div class="field">
        <label>Photo style</label>
        <div class="modes">
          <label class="mode"><input type="radio" name="mode" value="cutout" checked>
            <span><b>Remove background</b>
            <small>Subject is cut out and blended into the flyer (recommended).</small></span></label>
          <label class="mode"><input type="radio" name="mode" value="frame">
            <span><b>Keep background</b>
            <small>Photo is cropped into the round frame, like the original.</small></span></label>
        </div>
      </div>

      <button class="primary" id="go" type="submit">Create flyer</button>
      <div class="err" id="err"></div>
    </form>

    <div class="card">
      <div class="stage" id="stage">
        <div class="hint" id="hint">Your flyer will appear here.<br>Background removal takes ~10 seconds.</div>
      </div>
      <div class="actions" id="actions" style="display:none">
        <button class="ghost" id="dlpng" type="button">⬇ Download PNG</button>
        <button class="ghost" id="dljpg" type="button">⬇ Download JPG</button>
      </div>
      <div class="foot">{{w}} × {{h}} px · ready for WhatsApp, print or social</div>
    </div>
  </div>
</div>

<script>
const form=document.getElementById('f'), stage=document.getElementById('stage'),
      hint=document.getElementById('hint'), err=document.getElementById('err'),
      go=document.getElementById('go'), actions=document.getElementById('actions'),
      drop=document.getElementById('drop'), fileInput=document.getElementById('photo'),
      thumb=document.getElementById('thumb'), nameInput=document.getElementById('name');
let blob=null, lastName='flyer';

let thumbUrl=null;
fileInput.addEventListener('change',()=>{
  const f=fileInput.files[0]; if(!f) return;
  thumb.style.display='flex';
  if(thumbUrl){URL.revokeObjectURL(thumbUrl);thumbUrl=null;}
  const mb=(f.size/1048576).toFixed(1);
  thumbUrl=URL.createObjectURL(f);
  const ext=(f.name.split('.').pop()||'').toLowerCase();
  // browsers can't render HEIC/TIFF/RAW — show a badge instead of a broken image
  const noPreview=['heic','heif','hif','tif','tiff','avif','dng','cr2','cr3','nef','arw','orf',
                   'rw2','raf','srw','pef','psd','jp2'].includes(ext);
  thumb.innerHTML = noPreview
    ? '<span class="badge">'+ext.toUpperCase()+'</span><span>'+f.name+' · '+mb+' MB · ready</span>'
    : '<img src="'+thumbUrl+'" onerror="this.remove()"><span>'+f.name+' · '+mb+' MB</span>';
});
['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('hot')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('hot')}));
drop.addEventListener('drop',ev=>{
  if(ev.dataTransfer.files.length){fileInput.files=ev.dataTransfer.files;fileInput.dispatchEvent(new Event('change'));}
});

form.addEventListener('submit',async ev=>{
  ev.preventDefault();
  err.style.display='none';
  if(!fileInput.files.length){showErr('Please choose a photo first.');return;}
  if(!nameInput.value.trim()){showErr('Please type the name.');return;}
  go.disabled=true; go.textContent='Creating…';
  stage.innerHTML='<div class="hint"><div class="spinner"></div>Working on it — cutting out and blending…</div>';
  actions.style.display='none';
  try{
    const res=await fetch('/render',{method:'POST',body:new FormData(form)});
    if(!res.ok){throw new Error((await res.text())||('HTTP '+res.status));}
    blob=await res.blob();
    lastName=(nameInput.value.trim().toUpperCase().replace(/[^A-Z0-9]+/g,'-'))+'-flyer';
    stage.innerHTML='';
    const img=document.createElement('img'); img.src=URL.createObjectURL(blob); stage.appendChild(img);
    actions.style.display='flex';
  }catch(e){ showErr('Could not create the flyer: '+e.message);
    stage.innerHTML='<div class="hint">Nothing rendered yet.</div>'; }
  finally{ go.disabled=false; go.textContent='Create flyer'; }
});

function showErr(m){err.textContent=m;err.style.display='block';}
function save(blobUrl,name){const a=document.createElement('a');a.href=blobUrl;a.download=name;a.click();}
document.getElementById('dlpng').onclick=()=>{if(blob)save(URL.createObjectURL(blob),lastName+'.png');};
document.getElementById('dljpg').onclick=()=>{
  if(!blob) return;
  const i=new Image(); i.onload=()=>{
    const c=document.createElement('canvas'); c.width=i.width; c.height=i.height;
    const x=c.getContext('2d'); x.fillStyle='#fff'; x.fillRect(0,0,c.width,c.height); x.drawImage(i,0,0);
    c.toBlob(b=>save(URL.createObjectURL(b),lastName+'.jpg'),'image/jpeg',0.94);
  }; i.src=URL.createObjectURL(blob);
};
</script></body></html>
"""


@app.get('/')
def index():
    return Response(render_template_string(PAGE, w=CFG['canvas'][0], h=CFG['canvas'][1]),
                    mimetype='text/html')


@app.post('/render')
def render_flyer():
    photo = request.files.get('photo')
    name = (request.form.get('name') or '').strip()
    mode = request.form.get('mode', 'cutout')
    if mode not in ('cutout', 'frame'):
        mode = 'cutout'
    if photo is None or photo.filename == '':
        return Response('No photo uploaded.', status=400)
    if not name:
        return Response('The name is empty.', status=400)

    tmpdir = tempfile.mkdtemp(prefix='flyer-')
    src_path = os.path.join(tmpdir, 'in.png')
    cut_path = os.path.join(tmpdir, 'cut.png')
    try:
        # normalise the upload once — accepts any image format, rotates by EXIF,
        # keeps real transparency, and caps memory for huge camera files
        try:
            im = load_any(photo.read(), max_side=2400, keep_alpha=True)
        except UnreadableImage as exc:
            return Response(str(exc), status=400)
        except Exception:
            return Response('That image could not be opened — it may be damaged. '
                            'Try exporting it as JPG or PNG.', status=400)
        im.save(src_path, format='PNG')

        cutout = None
        if mode == 'cutout':
            worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template', 'cutout_worker.py')
            if not _cutout_slots.acquire(timeout=int(os.environ.get('CUTOUT_WAIT', '120'))):
                return Response('The line for background removal is full — try again in a '
                                'minute, or use "Keep background".', status=503)
            try:
                proc = subprocess.run([sys.executable, worker, src_path, cut_path],
                                      capture_output=True, text=True, timeout=240)
            finally:
                _cutout_slots.release()
            if proc.returncode != 0 or not os.path.exists(cut_path):
                traceback.print_tb = None
                print(proc.stderr[-1500:], file=sys.stderr)
                return Response('Background removal failed on this photo — try '
                                '"Keep background" or use another image.', status=500)
            cutout = Image.open(cut_path).convert('RGBA')

        img = render(src_path, name, mode, cutout=cutout)
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        buf.seek(0)
        fname = name.upper().replace(' ', '-') + '-flyer.png'
        return send_file(buf, mimetype='image/png', download_name=fname)
    except subprocess.TimeoutExpired:
        return Response('Background removal timed out — try a smaller photo.', status=504)
    except Exception as exc:
        traceback.print_exc()
        return Response(f'Could not create the flyer: {exc}', status=500)
    finally:
        for p in (src_path, cut_path):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


@app.errorhandler(413)
def too_big(_e):
    return Response('That file is larger than 64 MB. Resize it, or send a smaller copy.',
                    status=413)


@app.get('/healthz')
def healthz():
    import render as _r
    return {'ok': True, 'canvas': _r.CFG['canvas'], 'cutout_slots': CUTOUT_SLOTS}


@app.get('/formats')
def formats():
    return {'accepts': describe()}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, threaded=True)
