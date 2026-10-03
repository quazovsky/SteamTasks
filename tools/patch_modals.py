"""One-shot patch: replace every native confirm/alert/prompt in the dashboard page
with custom in-page dialogs.

Run from the repo root:
    python tools/patch_modals.py

It is idempotent: re-running reports "already patched" and does nothing.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "worthlesstask" / "web" / "page.py"

# --------------------------------------------------------------------------- CSS
CSS_ANCHOR = ".toast.error{border-color:rgba(226,154,163,.5);color:#ffd4da}"

CSS = """
/* Custom dialogs. The native confirm/alert/prompt cannot be styled, they freeze the
   page and they break the visual language, so every one is replaced by an in-page
   dialog built from the same liquid-glass material as the panels. */
.modal-scrim{position:fixed;inset:0;z-index:60;display:grid;place-items:center;padding:22px;
  background:rgba(3,4,6,.62);backdrop-filter:blur(16px) saturate(140%);-webkit-backdrop-filter:blur(16px) saturate(140%);
  opacity:0;transition:opacity .22s var(--ease)}
.modal-scrim.is-open{opacity:1}
.modal{position:relative;width:100%;max-width:440px;border-radius:var(--r-lg);padding:22px 22px 20px;
  border:1px solid var(--glass-brd);box-shadow:var(--shadow);
  background:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,0) 46%),
             linear-gradient(158deg,rgba(255,255,255,.085),rgba(255,255,255,.028)),rgba(10,11,14,.86);
  backdrop-filter:blur(34px) saturate(165%);-webkit-backdrop-filter:blur(34px) saturate(165%);
  transform:scale(.96) translateY(6px);opacity:0;transition:transform .22s var(--ease),opacity .22s var(--ease)}
.modal-scrim.is-open .modal{transform:none;opacity:1}
.modal:before{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;
  background:linear-gradient(180deg,rgba(255,255,255,.07),transparent 42%)}
.modal:after{content:"";position:absolute;inset:-1px;border-radius:calc(var(--r-lg) + 1px);pointer-events:none;
  border:1px solid rgba(255,255,255,.06)}
.modal-title{margin:0;font-size:17px;font-weight:600;letter-spacing:-.3px}
.modal-msg{margin:9px 0 0;color:var(--ink-2);font-size:13.5px;line-height:1.6}
.modal-input{margin-top:15px;width:100%}
.modal-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:20px}
.modal-actions .btn{min-width:106px}
@media (max-width:420px){.modal-scrim{padding:14px}.modal{padding:18px 16px 16px}
  .modal-actions{flex-direction:column-reverse}.modal-actions .btn{width:100%}}
"""

# -------------------------------------------------------------------------- HTML
HTML_ANCHOR = '<div id="toast" class="toast glass-float" role="status" hidden></div>'

HTML = HTML_ANCHOR + """
<div id="modalRoot" class="modal-scrim" hidden>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle" aria-describedby="modalMsg">
    <h2 class="modal-title" id="modalTitle"></h2>
    <p class="modal-msg" id="modalMsg"></p>
    <input class="modal-input" id="modalInput" type="text" hidden>
    <div class="modal-actions">
      <button class="btn" type="button" id="modalCancel"></button>
      <button class="btn primary" type="button" id="modalOk"></button>
    </div>
  </div>
</div>"""

# ----------------------------------------------------------------------------- JS
JS_ANCHOR = "document.addEventListener('click',e=>{const b=e.target.closest('[data-act]');"

JS = r"""/* ---- Custom dialogs -------------------------------------------------------
   Native confirm/alert/prompt are gone: they cannot be styled, they block the
   page and they do not belong to this visual language. Each of these returns a
   Promise, so callers must await them.
     showConfirm -> boolean
     showAlert   -> true
     showPrompt  -> string | null   (null when cancelled) */
const modal={root:$('modalRoot'),title:$('modalTitle'),msg:$('modalMsg'),input:$('modalInput'),
  ok:$('modalOk'),cancel:$('modalCancel'),opener:null,resolve:null};
function dialogOpen(opts,withInput){
  return new Promise(resolve=>{
    /* Only one dialog at a time: resolve any stale one as cancelled. */
    if(modal.resolve){const prev=modal.resolve;modal.resolve=null;prev(false)}
    modal.resolve=resolve;
    modal.opener=document.activeElement;
    text(modal.title,opts.title||'');
    text(modal.msg,opts.message||'');
    modal.input.hidden=!withInput;
    if(withInput){modal.input.value=opts.initial||'';modal.input.placeholder=opts.placeholder||'';modal.input.maxLength=Number(opts.maxLength)||256}
    modal.cancel.hidden=!!opts.hideCancel;
    setText(modal.cancel,opts.cancelText||t('dlg.cancel'));
    setText(modal.ok,opts.confirmText||t('dlg.ok'));
    modal.ok.className='btn '+(opts.danger?'danger':'primary');
    /* Lock scrolling without shifting the page. */
    document.documentElement.style.overflow='hidden';
    modal.root.hidden=false;
    requestAnimationFrame(()=>modal.root.classList.add('is-open'));
    if(withInput)modal.input.focus();
    else if(!modal.cancel.hidden)modal.cancel.focus();
    else modal.ok.focus();
  });
}
function dialogClose(result){
  if(!modal.resolve)return;
  const resolve=modal.resolve;modal.resolve=null;
  modal.root.classList.remove('is-open');
  document.documentElement.style.overflow='';
  setTimeout(()=>{modal.root.hidden=true;
    if(modal.opener&&modal.opener.focus){try{modal.opener.focus()}catch(_){}}},200);
  resolve(result);
}
const dialogCancel=()=>dialogClose(modal.input.hidden?false:null);
modal.ok.addEventListener('click',()=>dialogClose(modal.input.hidden?true:modal.input.value.trim()));
modal.cancel.addEventListener('click',dialogCancel);
modal.root.addEventListener('mousedown',e=>{if(e.target===modal.root)dialogCancel()});
document.addEventListener('keydown',e=>{
  if(!modal.resolve)return;
  if(e.key==='Escape'){e.preventDefault();dialogCancel();return}
  if(e.key==='Enter'&&e.target!==modal.ok&&e.target!==modal.cancel){e.preventDefault();modal.ok.click();return}
  if(e.key==='Tab'){
    /* Keep focus inside the dialog while it is open. */
    const f=[modal.ok,modal.cancel,modal.input].filter(el=>!el.hidden);
    const i=f.indexOf(document.activeElement);
    if(i<0||(e.shiftKey&&i===0)||(!e.shiftKey&&i===f.length-1)){
      e.preventDefault();f[e.shiftKey?f.length-1:0].focus();
    }
  }
},true);
function showConfirm(o){return dialogOpen(Object.assign({danger:false},o),false).then(v=>v===true)}
function showAlert(o){return dialogOpen(Object.assign({hideCancel:true},o),false).then(()=>true)}
function showPrompt(o){return dialogOpen(o,true).then(v=>v===null?null:v)}
"""

# ----------------------------------------------------------------- i18n additions
EN_ANCHOR = '"status.connected":"Panel connected","status.offline":"No connection to the panel",'
RU_ANCHOR = '"status.connected":"Панель подключена","status.offline":"Нет связи с панелью",'

EN_KEYS = (
    '"dlg.ok":"OK","dlg.cancel":"Cancel","dlg.delete":"Delete","dlg.end":"End",'
    '"dlg.delTitle":"Delete game?","dlg.delMsg":"The game will be removed from the library. '
    'Installed game files are not affected.","dlg.deleted":"Game removed from the library",'
    '"dlg.resetTitle":"End session?","dlg.resetMsg":"End the session and clear its record?",'
)

RU_KEYS = (
    '"dlg.ok":"ОК","dlg.cancel":"Отмена","dlg.delete":"Удалить","dlg.end":"Завершить",'
    '"dlg.delTitle":"Удалить игру?","dlg.delMsg":"Игра будет удалена из библиотеки. '
    'Файлы установленной игры не затрагиваются.","dlg.deleted":"Игра удалена из библиотеки",'
    '"dlg.resetTitle":"Завершить сессию?","dlg.resetMsg":"Завершить сессию и очистить запись о ней?",'
)


def replace_once(source: str, old: str, new: str, what: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"anchor for {what} found {count} times (expected 1): {old[:60]!r}")
    return source.replace(old, new, 1)


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")

    if "modalRoot" in source:
        print("already patched — nothing to do")
        return 0

    # CSS
    source = replace_once(source, CSS_ANCHOR, CSS_ANCHOR + CSS, "modal CSS")

    # HTML
    source = replace_once(source, HTML_ANCHOR, HTML, "modal HTML")

    # i18n
    source = replace_once(source, EN_ANCHOR, EN_ANCHOR + EN_KEYS, "en dialog keys")
    source = replace_once(source, RU_ANCHOR, RU_ANCHOR + RU_KEYS, "ru dialog keys")

    # Delete confirmation. The listener becomes async so await works.
    old_listener = "document.addEventListener('click',e=>{const b=e.target.closest('[data-act]');"
    new_listener = "document.addEventListener('click',async e=>{const b=e.target.closest('[data-act]');"
    source = replace_once(source, old_listener, JS + new_listener, "click listener + dialog JS")

    old_delete = (
        "if(kind==='delete'&&!confirm('Удалить игру из библиотеки? "
        "Файлы установленной игры не затрагиваются.'))return;"
    )
    new_delete = (
        "if(kind==='delete'&&!await showConfirm({title:t('dlg.delTitle'),message:t('dlg.delMsg'),"
        "confirmText:t('dlg.delete'),cancelText:t('dlg.cancel'),danger:true}))return;"
    )
    source = replace_once(source, old_delete, new_delete, "delete confirm")

    # Toast after a successful delete.
    old_toast = (
        "kind==='start'?'Запрос на запуск принят':kind==='prepare'?"
        "'EXE создан. Файл лежит рядом с программой — его можно запустить двойным щелчком, "
        "откроется окно игры.':null)"
    )
    new_toast = (
        "kind==='start'?'Запрос на запуск принят':kind==='prepare'?"
        "'EXE создан. Файл лежит рядом с программой — его можно запустить двойным щелчком, "
        "откроется окно игры.':kind==='delete'?t('dlg.deleted'):null)"
    )
    source = replace_once(source, old_toast, new_toast, "delete toast")

    # Reset-session confirmation.
    old_reset = (
        "$('resetSession').onclick=()=>{if(!confirm('Завершить сессию и очистить запись о ней?'))return;"
    )
    new_reset = (
        "$('resetSession').onclick=async()=>{if(!await showConfirm({title:t('dlg.resetTitle'),"
        "message:t('dlg.resetMsg'),confirmText:t('dlg.end'),cancelText:t('dlg.cancel'),danger:true}))return;"
    )
    source = replace_once(source, old_reset, new_reset, "reset confirm")

    TARGET.write_text(source, encoding="utf-8")
    print(f"patched {TARGET.relative_to(ROOT)} ({len(source)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
