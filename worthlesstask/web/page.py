"""Local dashboard page (single embedded document, no build step).

Two design languages live here on purpose:
* Home keeps the original liquid-glass landing (hero, moon, principles, flow).
* Games is the workspace: the dense matte system, scoped to ``#view-play`` so the
  two never bleed into each other.
The header carries the language switch and the theme switch (sun in the light
theme, moon in the dark one; the choice is remembered).
"""
PAGE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>SteamTasks</title><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%23ffffff'/%3E%3Cstop offset='1' stop-color='%23c9d4e4'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect x='6' y='6' width='52' height='52' rx='16' fill='url(%23g)' stroke='%239fb0c8' stroke-width='2'/%3E%3Cpath d='M22 40V26m10 14V26m10 14V26' stroke='%23232b3a' stroke-width='5' stroke-linecap='round'/%3E%3C/svg%3E">
<style>
:root{color-scheme:dark;
--void:#050507;--matte:#0a0b0e;
--ink:#f5f7fa;--ink-2:#c6ccd5;--ink-3:#8b9199;--ink-4:#5a6069;
--line:rgba(255,255,255,.085);--line-2:rgba(255,255,255,.16);
--glass-bg:linear-gradient(158deg,rgba(255,255,255,.078),rgba(255,255,255,.026));
--glass-brd:rgba(255,255,255,.10);--glass-inset:inset 0 1px 0 rgba(255,255,255,.13);
--blur:20px;
--r-lg:18px;--r-md:13px;--r-sm:10px;--pill:999px;
--ease:cubic-bezier(.22,.8,.3,1);
--shadow:inset 0 1px 0 rgba(255,255,255,.13),inset 0 -1px 0 rgba(0,0,0,.55),0 26px 64px -36px rgba(0,0,0,.95);
--glow:0 0 0 1px rgba(255,255,255,.5),0 0 0 6px rgba(255,255,255,.06)}
*{box-sizing:border-box}
html{background:var(--void);scroll-behavior:smooth}
body{margin:0;background:transparent;color:var(--ink);font:14px/1.55 Inter,"Segoe UI",system-ui,-apple-system,sans-serif;letter-spacing:.15px;min-height:100vh;overflow-x:hidden}
button,input,select{font:inherit;color:inherit}
button{cursor:pointer}
:focus-visible{outline:1px solid rgba(255,255,255,.55);outline-offset:2px;box-shadow:var(--glow);border-radius:8px}
button:disabled{cursor:default;opacity:.38}
[hidden]{display:none!important}
h1,h2,h3{margin:0;font-weight:600;letter-spacing:-.4px;line-height:1.2}
p{margin:0}
svg{display:block}
.ambient{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}
.pool{position:absolute;border-radius:50%;filter:blur(120px);animation:drift 26s ease-in-out infinite}
.pool.a{width:780px;height:780px;left:-320px;top:-360px;background:radial-gradient(circle,rgba(255,255,255,.09),transparent 66%)}
.pool.b{width:620px;height:620px;right:-280px;top:60px;background:radial-gradient(circle,rgba(255,255,255,.055),transparent 66%);animation-duration:32s;animation-delay:-6s}
.pool.c{width:900px;height:900px;left:22%;bottom:-620px;background:radial-gradient(circle,rgba(255,255,255,.05),transparent 68%);animation-duration:40s;animation-delay:-14s}
.pool.d{width:430px;height:430px;left:53%;top:4%;background:radial-gradient(circle,rgba(255,255,255,.05),transparent 64%);animation-duration:36s;animation-delay:-20s}
.grain{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.2;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='.34'/%3E%3C/svg%3E")}
.shell{position:relative;z-index:1}
.glass,.panel,.rail{position:relative;background:var(--glass-bg);border:1px solid var(--glass-brd);border-radius:var(--r-lg);box-shadow:var(--shadow);backdrop-filter:blur(var(--blur)) saturate(155%);-webkit-backdrop-filter:blur(var(--blur)) saturate(155%)}
.glass:before,.panel:before,.rail:before{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;background:linear-gradient(180deg,rgba(255,255,255,.07),transparent 46%)}
.glass-float{background:linear-gradient(158deg,rgba(255,255,255,.10),rgba(255,255,255,.035));backdrop-filter:blur(34px) saturate(165%);-webkit-backdrop-filter:blur(34px) saturate(165%);border:1px solid rgba(255,255,255,.14);box-shadow:inset 0 1px 0 rgba(255,255,255,.18),inset 0 -1px 0 rgba(0,0,0,.6),0 34px 80px -30px rgba(0,0,0,.98)}
.panel{overflow:hidden;transition:border-color .3s var(--ease),transform .3s var(--ease)}
.panel:hover{border-color:var(--line-2);transform:translateY(-2px)}
.nav{position:sticky;top:0;z-index:20;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;padding:11px max(26px,calc((100vw - 1260px)/2 + 26px));background:linear-gradient(180deg,rgba(9,10,13,.88),rgba(6,7,9,.72));backdrop-filter:blur(30px) saturate(160%);-webkit-backdrop-filter:blur(30px) saturate(160%);border-bottom:1px solid var(--line)}
.nav-left{display:flex;align-items:center;gap:12px;justify-self:start;min-width:0}
.nav-right{display:flex;align-items:center;justify-content:flex-end;justify-self:end;min-width:0}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:13px;letter-spacing:.6px;color:var(--ink);text-decoration:none}
.mark{width:22px;height:22px;flex:none;display:grid;place-items:center;color:var(--ink);opacity:.9}
.i{width:18px;height:18px;flex:none;fill:none;stroke:currentColor;stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}
.lang{display:inline-flex;align-items:center;gap:2px;padding:2px;border-radius:var(--pill);background:rgba(255,255,255,.03);border:1px solid var(--line)}
.lang-btn{border:0;background:transparent;color:var(--ink-4);font-size:10.5px;font-weight:700;letter-spacing:.6px;padding:4px 8px;border-radius:var(--pill);transition:color .2s var(--ease),background .2s var(--ease)}
.lang-btn:hover{color:var(--ink)}
.lang-btn[aria-pressed=true]{color:#0b0c0d;background:linear-gradient(160deg,#fbfcfd,#c8ccd1)}
.tabs{position:relative;display:flex;gap:2px;padding:3px;justify-self:center;border-radius:var(--pill);background:rgba(255,255,255,.03);border:1px solid var(--line)}
.tab{position:relative;z-index:1;display:inline-flex;align-items:center;gap:8px;border:0;background:transparent;color:var(--ink-3);padding:7px 15px;border-radius:var(--pill);font-size:12px;font-weight:600;white-space:nowrap;transition:color .2s var(--ease)}
.tab:hover{color:var(--ink)}
.tab[aria-selected=true]{color:#0b0c0d}
.tab-indicator{position:absolute;top:3px;left:0;height:calc(100% - 6px);width:0;border-radius:var(--pill);z-index:0;pointer-events:none;background:linear-gradient(160deg,#fbfcfd,#c8ccd1);box-shadow:0 7px 16px -10px #000,inset 0 1px 0 rgba(255,255,255,.9);transition:transform .4s var(--ease),width .4s var(--ease)}
.chip{display:flex;align-items:center;gap:9px;padding:7px 13px;border-radius:var(--pill);background:rgba(255,255,255,.045);border:1px solid var(--line);font-size:11px;color:var(--ink-2);white-space:nowrap;backdrop-filter:blur(14px)}
.chip .dot{width:7px;height:7px;border-radius:50%;background:#9bdfbc;box-shadow:0 0 10px #9bdfbc;flex:none}
.chip .dot.off{background:#e29aa3;box-shadow:0 0 10px #e29aa3;animation:breathe 1.5s ease-in-out infinite}
main{max-width:1260px;margin:0 auto;padding:0 26px 70px}
.view{will-change:auto}
.view-inner.is-entering{animation:viewIn .34s var(--ease) both}
.hero-stage{position:relative;display:flex;flex-direction:column;align-items:center;text-align:center;padding:54px 18px 0}
.eyebrow{display:inline-flex;align-items:center;gap:9px;font-size:10px;letter-spacing:2.4px;text-transform:uppercase;color:var(--ink-2);padding:7px 14px;border-radius:var(--pill);background:linear-gradient(160deg,rgba(255,255,255,.075),rgba(255,255,255,.02));border:1px solid var(--line-2);backdrop-filter:blur(12px)}
.eyebrow:before{content:"";width:5px;height:5px;border-radius:50%;background:var(--ink);box-shadow:0 0 10px rgba(255,255,255,.85);flex:none}
h1{position:relative;z-index:2;margin:26px 0 12px;letter-spacing:-.08em;line-height:.88;animation:fadeUp .7s .08s var(--ease) both}
.hero-word{display:block;font-size:clamp(52px,11vw,140px);font-weight:750;letter-spacing:-.09em;background:linear-gradient(180deg,#ffffff 2%,#b9c0c9 92%);color:transparent;background-clip:text;-webkit-background-clip:text;text-shadow:0 20px 52px rgba(255,255,255,.10)}
.hero-sub{display:block;margin-top:18px;font-size:clamp(12px,1.35vw,17px);letter-spacing:.42em;color:var(--ink-3);font-weight:600}
.lede{position:relative;z-index:2;color:var(--ink-3);font-size:14px;max-width:56ch;margin-top:14px;animation:fadeUp .6s .18s var(--ease) both}
.hero-actions{position:relative;z-index:3;display:flex;flex-wrap:wrap;justify-content:center;gap:10px;margin-top:28px;animation:fadeUp .6s .24s var(--ease) both}
.moon-scene{position:relative;z-index:1;width:min(440px,74vw);aspect-ratio:1;margin:26px auto 0;animation:moonFloat 9s ease-in-out infinite;filter:drop-shadow(0 -12px 46px rgba(255,255,255,.09))}
.moon-svg{position:relative;width:100%;height:100%;overflow:visible}
.mn-orbit ellipse{fill:none;stroke:rgba(255,255,255,.16);stroke-width:1;stroke-dasharray:1 12;transform-origin:200px 200px;animation:moonSpin 54s linear infinite}
.mn-stars circle{fill:#fff;animation:starPulse 4s ease-in-out infinite}
.mn-stars circle:nth-child(2){animation-delay:.6s}
.mn-stars circle:nth-child(3){animation-delay:1.1s}
.mn-stars circle:nth-child(4){animation-delay:1.7s}
.mn-stars circle:nth-child(5){animation-delay:2.2s}
.mn-craters circle{fill:#8b929c;opacity:.3}
.mn-craters circle.rim{fill:none;stroke:rgba(255,255,255,.26);stroke-width:1.2;opacity:1}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 344px;gap:20px;align-items:start;margin-top:26px}
.col{display:grid;gap:20px;min-width:0}
.head{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:18px 22px 14px}
.head h2{font-size:16px;display:flex;align-items:center;gap:11px}
.head small{color:var(--ink-4);font-size:12.5px;flex:none}
.counter{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:22px;padding:0 8px;border-radius:var(--pill);background:linear-gradient(160deg,rgba(255,255,255,.13),rgba(255,255,255,.045));border:1px solid var(--line-2);color:var(--ink);font-size:11.5px;font-weight:700;font-variant-numeric:tabular-nums;box-shadow:inset 0 1px 0 rgba(255,255,255,.16);transition:transform .25s var(--ease),box-shadow .25s var(--ease)}
.counter.bump{animation:counterPop .34s var(--ease)}
.body{padding:0 22px 22px}
.btn{position:relative;display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid transparent;background:var(--glass-bg);color:var(--ink);border-radius:var(--r-sm);padding:9px 14px;font-size:14px;font-weight:550;min-height:38px;white-space:nowrap}
.btn:hover:not(:disabled){background:rgba(255,255,255,.11)}
.btn:active:not(:disabled){background:rgba(255,255,255,.15)}
.btn.primary{padding:9px clamp(16px,1.6vw,24px);background:linear-gradient(170deg,#fdfdfe,#d9dde2 62%,#c8ccd2);color:#0a0b0d;border-color:transparent;box-shadow:inset 0 -1px 0 rgba(0,0,0,.09),0 12px 30px -14px rgba(255,255,255,.30),0 2px 8px rgba(0,0,0,.5)}
.btn.primary:hover:not(:disabled){background:linear-gradient(170deg,#ffffff,#e4e7eb 62%,#d2d6db);box-shadow:inset 0 -1px 0 rgba(0,0,0,.09),0 16px 38px -14px rgba(255,255,255,.42),0 2px 8px rgba(0,0,0,.5)}


.btn.danger{color:#e29aa3;border-color:transparent;background:rgba(226,154,163,.08)}
.btn.danger:hover:not(:disabled){background:rgba(226,154,163,.16)}
.btn.ghost{background:transparent;border-color:transparent;color:var(--ink-3)}
.btn.ghost:hover:not(:disabled){color:var(--ink);background:rgba(255,255,255,.06)}
.btn.small{min-height:32px;padding:6px 11px;font-size:12.5px;border-radius:9px}
.btn.wide{width:100%}
input,select{background:rgba(8,10,14,.55);border:1px solid var(--line-2);border-radius:var(--r-sm);padding:11px 13px;min-width:0;transition:border-color .18s var(--ease),box-shadow .18s var(--ease)}
input::placeholder{color:var(--ink-4)}
input:focus,select:focus{border-color:rgba(255,255,255,.42);box-shadow:0 0 0 3px rgba(255,255,255,.09);outline:none}
.search-row{display:flex;gap:10px}
.search-row input{flex:1}
.hint{color:var(--ink-4);font-size:12.5px;margin-top:11px}.hint:empty{display:none}
.status-line{min-height:24px;padding-top:12px;font-size:12.5px;color:var(--ink-3)}
.results{display:grid;gap:9px;max-height:352px;overflow:auto;padding-right:4px}
.result-area{min-height:120px;margin-top:10px}
.result{display:flex;align-items:center;gap:14px;width:100%;text-align:left;padding:13px;border-radius:var(--r-md);border:1px solid var(--line);background:rgba(255,255,255,.028);transition:border-color .18s var(--ease),background .18s var(--ease),transform .18s var(--ease)}
.result:hover{border-color:var(--line-2);background:rgba(255,255,255,.06)}
.result[aria-pressed=true]{border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.085);transform:translateX(3px)}
.result-body{flex:1;min-width:0}
.result .name{font-weight:600;font-size:14.5px;overflow-wrap:anywhere}
.result .meta{color:var(--ink-4);font-size:12px;margin-top:3px;overflow-wrap:anywhere}
.check{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;flex:none;background:rgba(255,255,255,.06);border:1px solid var(--line-2)}
.result[aria-pressed=true] .check{background:linear-gradient(160deg,#fdfdfe,#ccd0d6);border-color:transparent}
.result[aria-pressed=true] .check:after{content:"";width:10px;height:5px;border-left:2px solid #0b0c0d;border-bottom:2px solid #0b0c0d;transform:rotate(-45deg) translate(1px,-1px)}
.empty{display:grid;place-items:center;min-height:120px;padding:24px;text-align:center;color:var(--ink-4);font-size:13px;border:1px dashed var(--line);border-radius:var(--r-md);background:rgba(255,255,255,.018)}
.pulse{height:56px;border-radius:var(--r-md);background:linear-gradient(90deg,rgba(255,255,255,.03),rgba(255,255,255,.09),rgba(255,255,255,.03));background-size:220% 100%;animation:sweep 1.3s linear infinite}
.footer-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:15px}
.sel-label{flex:1;min-width:0;font-size:13px;color:var(--ink-3);overflow-wrap:anywhere}
.library{display:grid;gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--r-md);overflow:hidden}
.game{display:flex;flex-wrap:wrap;align-items:center;gap:10px 12px;padding:12px 14px;background:rgba(4,5,7,.55);transition:background .2s var(--ease)}
.game:hover{background:rgba(255,255,255,.042)}
.game.active{background:rgba(255,255,255,.062);box-shadow:inset 2px 0 0 rgba(255,255,255,.72)}
.icon-box{width:40px;height:40px;border-radius:11px;flex:none;display:grid;place-items:center;overflow:hidden;background:rgba(255,255,255,.06);border:1px solid var(--line-2);color:var(--ink-4);font-size:11px;font-weight:700}
.icon-box img{width:100%;height:100%;object-fit:cover;transition:transform .4s var(--ease)}
.game-info{flex:1 1 220px;min-width:0}
.game-name{font-weight:600;font-size:15px;overflow-wrap:anywhere}
.game-meta{color:var(--ink-4);font-size:12px;margin-top:2px;overflow-wrap:anywhere}
.badge{flex:none;padding:5px 11px;border-radius:var(--pill);font-size:11px;font-weight:600;border:1px solid rgba(155,223,188,.32);background:rgba(155,223,188,.14);color:#9bdfbc}
.badge.warn{border-color:rgba(210,186,130,.32);background:rgba(210,186,130,.13);color:#d2ba82}
.badge.run{border-color:rgba(255,255,255,.28);background:rgba(255,255,255,.10);color:var(--ink);animation:halo 2.8s ease-out infinite}
.reason{font-size:12.5px;color:#d2ba82;padding:10px 13px;border-radius:10px;flex:1 1 100%;background:rgba(210,186,130,.07);border:1px solid rgba(210,186,130,.2)}
.game-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end;margin-left:auto}
.exe-row{display:flex;gap:8px;flex:1 1 100%}
.exe-row input{flex:1;min-width:0}
.icon-picker{display:none}
.session-name{font-size:21px;font-weight:600;letter-spacing:-.5px;margin:16px 0 7px;overflow-wrap:anywhere}
.session-state{min-height:23px;font-size:12.5px;color:var(--ink)}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:1px;margin:16px 0;border-radius:var(--r-md);overflow:hidden;background:var(--line);border:1px solid var(--line)}
.stat{padding:14px;background:rgba(0,0,0,.42)}
.stat small{display:block;color:var(--ink-4);font-size:11px;letter-spacing:.4px;text-transform:uppercase}
.stat strong{display:block;margin-top:5px;font-size:19px;font-weight:600;font-variant-numeric:tabular-nums}
.session-note{min-height:56px;font-size:12.5px;color:var(--ink-3);margin:12px 0 14px}
.session-actions{display:grid;gap:9px}
.queue-settings{display:flex;align-items:center;gap:11px;color:var(--ink-3);font-size:12.5px;margin-bottom:14px}
.queue-settings input{width:78px;padding:8px 10px}
.queue{list-style:none;margin:0 0 14px;padding:0;display:grid;gap:8px;min-height:34px}
.queue-item{display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:12px;position:relative;overflow:hidden;border:1px solid var(--line);background:rgba(255,255,255,.028);font-size:13px;cursor:grab;transition:border-color .18s var(--ease),background .18s var(--ease),opacity .18s var(--ease),box-shadow .18s var(--ease)}
.queue-item:active{cursor:grabbing}
.queue-item.dragging{opacity:.4;border-style:dashed;cursor:grabbing}
.queue-item.drop-before{box-shadow:0 -2px 0 0 rgba(255,255,255,.6)}
.queue-item.drop-after{box-shadow:0 2px 0 0 rgba(255,255,255,.6)}
.queue-item.current{border-color:rgba(255,255,255,.42);background:rgba(255,255,255,.075)}
.q-grip{color:var(--ink-4);font-size:11px;letter-spacing:-1px;flex:none;user-select:none;line-height:1}
.q-bar{position:absolute;left:0;bottom:0;height:2px;width:0;background:linear-gradient(90deg,rgba(255,255,255,.25),rgba(255,255,255,.8));transition:width .9s linear}
.q-num{width:24px;height:24px;border-radius:9px;display:grid;place-items:center;flex:none;font-size:11.5px;font-weight:700;background:rgba(255,255,255,.06);border:1px solid var(--line-2);color:var(--ink-3)}
.queue-item.current .q-num{background:linear-gradient(160deg,#fdfdfe,#ccd0d6);color:#0b0c0d;border-color:transparent}
.q-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.q-min{color:var(--ink-4);font-size:11px;flex:none;font-variant-numeric:tabular-nums}
.q-order{display:grid;flex:none}
.q-move,.q-del{border:0;background:transparent;color:var(--ink-4);padding:1px 5px;border-radius:6px;line-height:1.15;font-size:10px}
.q-del{padding:2px 6px;font-size:13px;border-radius:7px}
.q-move:hover:not(:disabled),.q-del:hover:not(:disabled){color:var(--ink);background:rgba(255,255,255,.08)}
.q-del:hover:not(:disabled){color:#e29aa3}
.queue-actions{display:grid;grid-template-columns:1fr auto;gap:9px}
.queue-status{min-height:22px;font-size:12.5px;color:var(--ink-3);margin-top:12px}
.alert{border:1px solid rgba(226,154,163,.35);background:rgba(226,154,163,.1);color:#ffd4da;border-radius:var(--r-md);padding:14px 17px;font-size:13.5px;margin-bottom:20px}
.toast{position:fixed;right:26px;bottom:26px;z-index:40;max-width:390px;padding:15px 18px;border-radius:var(--r-md);font-size:13.5px;animation:fadeUp .3s both}
.toast.error{border-color:rgba(226,154,163,.5);color:#ffd4da}
@keyframes fadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes viewIn{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:none}}
@keyframes pop{from{opacity:0;transform:scale(.965)}to{opacity:1;transform:none}}
@keyframes slideIn{from{opacity:0;transform:translateX(-9px)}to{opacity:1;transform:none}}
@keyframes breathe{0%,100%{opacity:1}50%{opacity:.32}}
@keyframes halo{0%{box-shadow:0 0 0 0 rgba(255,255,255,.22)}70%{box-shadow:0 0 0 7px rgba(255,255,255,0)}100%{box-shadow:0 0 0 0 rgba(255,255,255,0)}}
@keyframes drift{0%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(3.5%,-2.5%,0) scale(1.06)}100%{transform:translate3d(0,0,0) scale(1)}}
@keyframes sweep{to{background-position:-220% 0}}
@keyframes moonFloat{0%,100%{transform:translateY(0) rotate(-1.2deg)}50%{transform:translateY(-10px) rotate(1.2deg)}}
@keyframes moonSpin{to{transform:rotate(360deg)}}
@keyframes starPulse{0%,100%{opacity:.22}50%{opacity:.9}}
@keyframes counterPop{0%{transform:scale(.86)}60%{transform:scale(1.12)}100%{transform:scale(1)}}
@keyframes livePulse{0%,100%{box-shadow:0 0 0 0 rgba(255,140,60,.32)}50%{box-shadow:0 0 0 7px rgba(255,140,60,0)}}
.btn.is-running{border-color:transparent;background:rgba(255,140,60,.14);color:#c05a10;opacity:1;animation:livePulse 2.2s ease-out infinite}
[data-theme=dark] .btn.is-running{background:rgba(255,140,60,.16);color:#ffab5e}
.result{animation:slideIn .26s var(--ease) both}
.queue-item{animation:pop .24s var(--ease) both}
@media (max-width:1000px){.layout{grid-template-columns:minmax(0,1fr)}}
@media (max-width:860px){.nav{grid-template-columns:1fr auto;row-gap:10px;padding:11px 16px}.tabs{grid-row:2;grid-column:1/-1;justify-self:stretch;width:100%}.tab{flex:1;justify-content:center;padding:8px 10px}main{padding:0 16px 56px}.hero-stage{padding-top:38px}.moon-scene{width:min(360px,80vw);margin-top:22px}}
@media (max-width:560px){.brand-name{display:none}.hero-sub{letter-spacing:.3em;font-size:10px}.lede{font-size:13px}.stats{grid-template-columns:1fr}.footer-row{flex-direction:column;align-items:stretch}.sel-label{width:100%}.footer-row .btn{width:100%}.queue-actions{grid-template-columns:1fr}.search-row{flex-direction:column}.head{padding:16px 16px 12px}.body{padding:0 16px 18px}.game{padding:12px}.game-actions{margin-left:0;width:100%;justify-content:flex-start}.exe-row{flex-direction:column}}
@media (prefers-reduced-motion:reduce){*{animation-duration:.001s!important;transition-duration:.001s!important}}

.gridlines{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.55;background-image:linear-gradient(rgba(18,24,34,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(18,24,34,.04) 1px,transparent 1px);background-size:68px 68px;-webkit-mask-image:radial-gradient(88% 58% at 50% 26%,#000,transparent 76%);mask-image:radial-gradient(88% 58% at 50% 26%,#000,transparent 76%)}
.vignette{position:fixed;inset:0;z-index:0;pointer-events:none;background:radial-gradient(125% 82% at 50% -6%,transparent 46%,rgba(90,105,130,.16) 100%)}
.principles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:38px 0 0;width:100%;text-align:left;animation:fadeUp .6s .3s var(--ease) both}
.principle{padding:20px 20px 22px;transition:border-color .3s var(--ease),transform .3s var(--ease)}
.principle:hover{border-color:rgba(255,255,255,.22);transform:translateY(-2px)}
.pr-ic{display:grid;place-items:center;width:34px;height:34px;border-radius:11px;color:var(--ink-2);border:1px solid var(--line-2);background:linear-gradient(160deg,rgba(255,255,255,.075),rgba(255,255,255,.02));box-shadow:inset 0 1px 0 rgba(255,255,255,.14)}
.pr-ic .i{width:17px;height:17px}
.principle h3{margin:15px 0 7px;font-size:14.5px;font-weight:600;letter-spacing:-.2px}
.principle p{color:var(--ink-3);font-size:13px;line-height:1.55}
.flow{margin:16px 0 0;padding:22px 22px 24px;width:100%;text-align:left;border-radius:var(--r-lg);border:1px solid var(--line);background:linear-gradient(180deg,rgba(255,255,255,.03),rgba(255,255,255,0) 60%),rgba(255,255,255,.03);box-shadow:inset 0 1px 0 rgba(255,255,255,.06);animation:fadeUp .6s .36s var(--ease) both}
.flow-head{display:flex;align-items:center;gap:14px;margin-bottom:20px}
.flow-eyebrow{font-size:10px;letter-spacing:2.2px;text-transform:uppercase;color:var(--ink-3);white-space:nowrap;font-weight:600}
.flow-head:after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--line-2),transparent)}
.flow-steps{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;position:relative}
.flow-steps:before{content:"";position:absolute;left:26px;right:26px;top:17px;height:1px;background:linear-gradient(90deg,transparent,var(--line-2) 10%,var(--line-2) 90%,transparent)}
.fs-ic{position:relative;display:grid;place-items:center;width:34px;height:34px;border-radius:11px;color:var(--ink);background:#080a0d;border:1px solid var(--line-2);box-shadow:inset 0 1px 0 rgba(255,255,255,.1),0 8px 18px -12px #000}
.fs-ic .i{width:17px;height:17px}
.fs-t{display:block;margin-top:13px;font-size:13.5px;font-weight:600;color:var(--ink)}
.fs-d{display:block;margin-top:5px;color:var(--ink-2);font-size:12.5px;line-height:1.5}

.icon-set{position:absolute;width:0;height:0;overflow:hidden}
.i.sm{width:15px;height:15px}
.bl{white-space:nowrap}
.hero-meta{display:flex;justify-content:center}
.flow-step{position:relative}
.modal-title{margin:0;font-size:17px;font-weight:600;letter-spacing:-.3px}
.modal-msg{margin:9px 0 0;color:var(--ink-2);font-size:13.5px;line-height:1.6}
.modal-input{margin-top:15px;width:100%}
.modal-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:20px}
.modal-actions .btn{min-width:106px}
.stack{display:grid;gap:16px}
.split{display:grid;grid-template-columns:minmax(0,1.72fr) minmax(280px,1fr);gap:16px;align-items:start}
.page-head{display:flex;align-items:baseline;gap:12px;margin:24px 0 14px;flex-wrap:wrap}
.page-head h1{font-size:17px;font-weight:600;letter-spacing:-.2px}
.page-head p{color:var(--ink-3);font-size:13px}
.session-top{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;flex-wrap:wrap}
.session-top .session-actions{display:flex;gap:8px;flex:none;margin-top:0}
@media (max-width:1000px){.split{grid-template-columns:minmax(0,1fr)}}
@media (max-width:620px){.session-top .session-actions{width:100%}.session-top .session-actions .btn{flex:1}}
@media (max-width:760px){.principles{grid-template-columns:1fr}.flow-steps{grid-template-columns:1fr 1fr}.flow-steps:before{display:none}}
@media (max-width:420px){.modal-actions{flex-direction:column-reverse}.modal-actions .btn{width:100%}}

.theme{width:32px;height:32px;flex:none;display:grid;place-items:center;padding:0;border:1px solid var(--line-2);border-radius:10px;background:rgba(255,255,255,.04);color:var(--ink-2);transition:color .18s var(--ease),background .18s var(--ease)}
.theme:hover{color:var(--ink)}
.theme .i{width:16px;height:16px;grid-area:1/1;transition:opacity .2s var(--ease),transform .3s var(--ease)}
.theme .i-moon{opacity:0;transform:scale(.6) rotate(-40deg)}
[data-theme=dark] .theme .i-sun{opacity:0;transform:scale(.6) rotate(40deg)}
[data-theme=dark] .theme .i-moon{opacity:1;transform:none}
/* ---------- light theme ---------- */
[data-theme=light]{color-scheme:light;
--void:#f4f0e8;--matte:#ece5d8;--matte-2:#e3dacb;--matte-3:#d9cdbc;
--ink:#140f09;--ink-2:#3d3224;--ink-3:#665643;--ink-4:#8c7860;
--line:rgba(20,15,9,.10);--line-2:rgba(20,15,9,.18);
--glass-bg:linear-gradient(158deg,rgba(255,255,255,.85),rgba(255,255,255,.6));
--glass-brd:rgba(20,15,9,.10);--glass-inset:inset 0 1px 0 rgba(255,255,255,.9);
--shadow:0 20px 50px -25px rgba(50,35,20,.14),0 4px 14px -6px rgba(50,35,20,.08);
--glow:0 0 0 1px rgba(192,83,8,.5),0 0 0 6px rgba(192,83,8,.12)}
[data-theme=light] .nav{background:rgba(244,240,232,.92);border-bottom-color:var(--line);box-shadow:0 10px 30px -15px rgba(50,35,20,.1)}
[data-theme=light] .gridlines{opacity:.2;background-image:linear-gradient(rgba(20,15,9,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(20,15,9,.05) 1px,transparent 1px)}
[data-theme=light] .vignette{background:radial-gradient(125% 82% at 50% -6%,transparent 42%,rgba(200,185,165,.3) 100%)}
[data-theme=light] .hero-word{background-image:linear-gradient(180deg,#140f09 2%,#5a4a38 92%);color:transparent;background-clip:text;-webkit-background-clip:text}
[data-theme=light] .hero-sub{color:var(--ink-3)}
[data-theme=light] .lede{color:var(--ink-2)}
[data-theme=light] .principle{background:rgba(255,255,255,.7);border-color:var(--line)}
[data-theme=light] .pr-ic{background:#fff;border-color:var(--line-2);color:var(--ink)}
[data-theme=light] .flow{background:rgba(255,255,255,.75);border-color:var(--line);box-shadow:var(--shadow)}
[data-theme=light] .flow-eyebrow{color:var(--ink-3)}
[data-theme=light] .fs-ic{background:#fff;border-color:var(--line-2);color:var(--ink);box-shadow:0 6px 16px -8px rgba(0,0,0,.15)}
[data-theme=light] .fs-t{color:var(--ink)}
[data-theme=light] .fs-d{color:var(--ink-2)}
[data-theme=light] .tabs{background:rgba(0,0,0,.04);border-color:var(--line)}
[data-theme=light] .tab{color:var(--ink-3)}
[data-theme=light] .tab[aria-selected=true]{color:#fff}
[data-theme=light] .tab-indicator{background:linear-gradient(160deg,#e06a14,#c05308 62%,#a84200);box-shadow:0 6px 16px -6px rgba(192,83,8,.5)}
[data-theme=light] .theme{background:rgba(0,0,0,.04);border-color:var(--line-2);color:var(--ink-2)}
[data-theme=light] .lang{background:rgba(0,0,0,.04);border-color:var(--line)}
[data-theme=light] .lang-btn{color:var(--ink-3)}
[data-theme=light] .lang-btn[aria-pressed=true]{color:#fff;background:linear-gradient(160deg,#e06a14,#c05308 62%,#a84200)}
[data-theme=light] .chip{background:rgba(255,255,255,.7);border-color:var(--line)}
/* ---------- dark theme: the same layout, graphite + orange ---------- */
[data-theme=dark]{color-scheme:dark;
--void:#08090b;--matte:#101317;--matte-2:#14181d;--matte-3:#1a1f25;
--ink:#eef1f6;--ink-2:#c3cad5;--ink-3:#8d96a4;--ink-4:#6b7482;
--line:rgba(255,255,255,.075);--line-2:rgba(255,255,255,.14);
--glass-brd:rgba(255,255,255,.09);--glass-inset:inset 0 1px 0 rgba(255,255,255,.08);
--shadow:inset 0 1px 0 rgba(255,255,255,.06),inset 0 -1px 0 rgba(0,0,0,.55),0 30px 70px -34px rgba(0,0,0,.9),0 4px 14px -6px rgba(0,0,0,.6);
--glow:0 0 0 1px rgba(255,150,70,.5),0 0 0 6px rgba(255,140,60,.12)}
[data-theme=dark] :focus-visible{outline-color:rgba(255,150,70,.6)}
[data-theme=dark] .gridlines{background-image:linear-gradient(rgba(255,212,156,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(255,212,156,.04) 1px,transparent 1px)}
[data-theme=dark] .vignette{background:radial-gradient(125% 82% at 50% -6%,transparent 42%,rgba(0,0,0,.62) 100%)}
[data-theme=dark] .pool.a{background:radial-gradient(circle,rgba(255,124,32,.15),transparent 66%)}
[data-theme=dark] .pool.b{background:radial-gradient(circle,rgba(255,110,26,.10),transparent 66%)}
[data-theme=dark] .pool.c{background:radial-gradient(circle,rgba(255,138,58,.09),transparent 68%)}
[data-theme=dark] .pool.d{background:radial-gradient(circle,rgba(190,200,220,.07),transparent 64%)}
[data-theme=dark] .grain{opacity:.16}
[data-theme=dark] .glass,[data-theme=dark] .panel,[data-theme=dark] .rail{background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,0) 52%),linear-gradient(158deg,rgba(255,140,60,.055),rgba(255,255,255,.012)),rgba(15,18,22,.66);box-shadow:var(--shadow)}
[data-theme=dark] .glass:before,[data-theme=dark] .panel:before,[data-theme=dark] .rail:before{background:linear-gradient(112deg,rgba(255,255,255,.07),rgba(255,255,255,0) 36%,rgba(255,255,255,0) 64%,rgba(255,140,60,.035))}
[data-theme=dark] .glass:after,[data-theme=dark] .panel:after,[data-theme=dark] .rail:after{box-shadow:inset 0 0 0 1px rgba(255,255,255,.035)}
[data-theme=dark] .panel:hover{border-color:rgba(255,150,70,.28)}
[data-theme=dark] .glass-2{background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,0) 50%),linear-gradient(158deg,rgba(255,140,60,.04),rgba(255,255,255,.01)),rgba(20,24,29,.7);box-shadow:inset 0 1px 0 rgba(255,255,255,.07),inset 0 -1px 0 rgba(0,0,0,.5),0 20px 46px -30px rgba(0,0,0,.8)}
[data-theme=dark] .glass-2:before{background:linear-gradient(118deg,rgba(255,255,255,.055),transparent 40%,transparent 70%,rgba(255,140,60,.02))}
[data-theme=dark] .glass-float{background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,0) 50%),linear-gradient(158deg,rgba(255,140,60,.08),rgba(255,255,255,.02)),rgba(13,16,20,.72);border-color:rgba(255,255,255,.11);box-shadow:inset 0 1px 0 rgba(255,255,255,.07),inset 0 -1px 0 rgba(0,0,0,.5),0 36px 84px -30px rgba(0,0,0,.9),0 0 0 1px rgba(0,0,0,.4)}
[data-theme=dark] .nav{background:linear-gradient(180deg,rgba(12,15,19,.86),rgba(8,10,13,.72));border-bottom-color:rgba(255,255,255,.07);box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 20px 46px -34px rgba(0,0,0,.95)}
[data-theme=dark] .lang{background:rgba(255,255,255,.04)}
[data-theme=dark] .lang-btn[aria-pressed=true]{color:#14100b;background:linear-gradient(160deg,#ffa64d,#ff7a18 62%,#e05e00)}
[data-theme=dark] .tabs{background:rgba(255,255,255,.04);box-shadow:inset 0 0 0 1px var(--line),inset 0 1px 0 rgba(255,255,255,.04)}
[data-theme=dark] .tab[aria-selected=true]{color:#14100b}
[data-theme=dark] .tab-indicator{background:linear-gradient(160deg,#ffa64d,#ff7a18 62%,#e05e00);box-shadow:0 8px 20px -10px rgba(255,122,24,.7),inset 0 1px 0 rgba(255,255,255,.35)}
[data-theme=dark] .chip{background:linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.015));box-shadow:inset 0 0 0 1px var(--line),inset 0 1px 0 rgba(255,255,255,.05)}
[data-theme=dark] .eyebrow{background:linear-gradient(160deg,rgba(255,140,60,.1),rgba(255,255,255,.015))}
[data-theme=dark] .eyebrow:before{background:#ff8a2b;box-shadow:0 0 12px rgba(255,138,43,.8)}
/* ``background-image`` on purpose: the ``background`` shorthand would reset
   ``background-clip:text`` and the heading would render as a solid block. */
[data-theme=dark] .hero-word{background-image:linear-gradient(180deg,#fff 2%,#8a919c 92%);color:transparent;background-clip:text;-webkit-background-clip:text;text-shadow:none}
[data-theme=dark] .moon-scene{filter:sepia(.32) saturate(1.1) hue-rotate(-12deg) drop-shadow(0 -14px 50px rgba(255,140,60,.12))}
[data-theme=dark] .principle:hover{border-color:rgba(255,150,70,.3)}
[data-theme=dark] .pr-ic{background:linear-gradient(160deg,rgba(255,140,60,.1),rgba(255,255,255,.02));box-shadow:inset 0 1px 0 rgba(255,255,255,.08)}
[data-theme=dark] .flow{background:linear-gradient(180deg,rgba(255,255,255,.03),rgba(255,255,255,0) 60%),rgba(255,255,255,.028);box-shadow:inset 0 1px 0 rgba(255,255,255,.045)}
[data-theme=dark] .fs-ic{background:linear-gradient(160deg,rgba(255,140,60,.1),rgba(255,255,255,.02))}
[data-theme=dark] .counter{background:rgba(255,255,255,.06);box-shadow:inset 0 0 0 1px rgba(255,255,255,.05)}
[data-theme=dark] .btn{border-color:transparent;background:linear-gradient(158deg,rgba(255,140,60,.06),rgba(255,255,255,.02)),rgba(255,255,255,.045)}
[data-theme=dark] .btn:hover:not(:disabled){background:rgba(255,255,255,.08)}
[data-theme=dark] .btn.primary{background:linear-gradient(170deg,#ff9a3c,#e2560a 72%);color:#1a0f05;border-color:transparent;box-shadow:inset 0 -1px 0 rgba(120,50,0,.45),0 14px 34px -16px rgba(255,110,20,.55),0 2px 10px rgba(0,0,0,.5)}
[data-theme=dark] .btn.primary:hover:not(:disabled){background:linear-gradient(170deg,#ffa64d,#ef6410 72%);box-shadow:inset 0 -1px 0 rgba(120,50,0,.45),0 18px 42px -16px rgba(255,120,30,.65),0 2px 10px rgba(0,0,0,.5)}
[data-theme=dark] .btn.danger{color:#ff9a94;border-color:rgba(255,110,100,.35);background:rgba(255,90,80,.1)}
[data-theme=dark] .btn.danger:hover:not(:disabled){background:rgba(255,90,80,.18);border-color:rgba(255,120,110,.55)}
[data-theme=dark] .btn.ghost:hover:not(:disabled){background:rgba(255,255,255,.06)}
[data-theme=dark] input,[data-theme=dark] select{background:rgba(255,255,255,.05)}
[data-theme=dark] input:focus,[data-theme=dark] select:focus{border-color:rgba(255,150,70,.45);box-shadow:0 0 0 3px rgba(255,140,60,.14)}
[data-theme=dark] .result{background:rgba(255,255,255,.028)}
[data-theme=dark] .result:hover{background:rgba(255,255,255,.055)}
[data-theme=dark] .result[aria-pressed=true]{border-color:rgba(255,150,70,.45);background:rgba(255,140,60,.10)}
[data-theme=dark] .check{background:rgba(255,255,255,.06)}
[data-theme=dark] .check .i{color:#0d0f12}
[data-theme=dark] .result[aria-pressed=true] .check{background:linear-gradient(160deg,#ffa64d,#ff7a18 65%,#e05e00);box-shadow:0 0 14px -4px rgba(255,122,24,.8)}
[data-theme=dark] .empty{background:rgba(255,255,255,.016)}
[data-theme=dark] .pulse{background:linear-gradient(90deg,rgba(255,255,255,.03),rgba(255,140,60,.12),rgba(255,255,255,.03))}
[data-theme=dark] .game{background:rgba(255,255,255,.032)}
[data-theme=dark] .game:hover{background:rgba(255,255,255,.05)}
[data-theme=dark] .game.active{background:rgba(255,140,60,.09);box-shadow:inset 2px 0 0 #ff8a2b}
[data-theme=dark] .icon-box{background:rgba(255,255,255,.05)}
[data-theme=dark] .badge{border-color:rgba(46,180,120,.35);background:rgba(46,180,120,.14);color:#7fe0b4}
[data-theme=dark] .badge.warn{border-color:rgba(226,168,60,.4);background:rgba(226,168,60,.14);color:#ffd08a}
[data-theme=dark] .badge.run{border-color:rgba(255,150,70,.4);background:rgba(255,140,60,.16);color:#ffcf9f}
[data-theme=dark] .reason{color:#ffd08a;background:rgba(226,168,60,.1);border-color:rgba(226,168,60,.28)}
[data-theme=dark] .stat{background:rgba(255,255,255,.032)}
[data-theme=dark] .queue-item{background:rgba(255,255,255,.03)}
[data-theme=dark] .queue-item.current{border-color:rgba(255,150,70,.42);background:rgba(255,140,60,.09)}
[data-theme=dark] .queue-item.drop-before{box-shadow:0 -2px 0 0 rgba(255,150,70,.7)}
[data-theme=dark] .queue-item.drop-after{box-shadow:0 2px 0 0 rgba(255,150,70,.7)}
[data-theme=dark] .q-grip{background-image:radial-gradient(circle,rgba(255,255,255,.5) 1px,transparent 1.15px)}
[data-theme=dark] .q-bar{background:linear-gradient(90deg,rgba(255,140,60,.3),#ff8a2b)}
[data-theme=dark] .q-move:hover:not(:disabled),[data-theme=dark] .q-del:hover:not(:disabled){background:rgba(255,255,255,.07)}
[data-theme=dark] .q-del:hover:not(:disabled){color:#ff9a94}
[data-theme=dark] .alert{border-color:rgba(255,110,100,.4);background:rgba(255,90,80,.12);color:#ffc9c4}
[data-theme=dark] .toast.error{border-color:rgba(255,110,100,.5);color:#ffc9c4}
[data-theme=dark] .modal-scrim{background:rgba(6,7,9,.78)}
[data-theme=dark] .modal{background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,0) 46%),linear-gradient(158deg,rgba(255,140,60,.07),rgba(255,255,255,.015)),rgba(15,18,22,.88)}
[data-theme=dark] .modal:after{border-color:rgba(255,255,255,.05)}

/* ============================================================================
   Games view: the dense matte system, scoped to #view-play
   (Home keeps the restored look above)
   ========================================================================= */
/* ============================================================================
   Games view: the dense matte system, scoped to #view-play
   (Home keeps the restored look above)
   ========================================================================= */
#view-play{
  color-scheme:light;
  color:var(--ink);
  background:var(--bg);
  --bg:#f3efe7; --surface:#ffffff; --surface-2:#f5f0e7; --surface-3:#e8e1d3;
  --line:#d6ccbb; --line-2:#bfae98;
  --ink:#140f09; --ink-2:#3d3224; --ink-3:#665643;
  --accent:#c05308; --accent-ink:#ffffff; --accent-soft:rgba(192,83,8,.12);
  --ok:#1f7041; --ok-soft:rgba(31,112,65,.12);
  --warn:#8f6d1b; --warn-soft:rgba(143,109,27,.12);
  --danger:#a83834; --danger-soft:rgba(168,56,52,.12);
  --focus:rgba(192,83,8,.55);
  --r:12px; --r-sm:8px;
  --shadow:0 8px 24px -12px rgba(45,30,14,.12),inset 0 1px 0 rgba(255,255,255,.9);
}
[data-theme=dark] #view-play{
  color-scheme:dark;
  color:var(--ink);
  background:var(--bg);
  --bg:#0b0907; --surface:#13100b; --surface-2:#1b150e; --surface-3:#251c12;
  --line:#2b2218; --line-2:#40311f;
  --ink:#f2e9dc; --ink-2:#c8ba9f; --ink-3:#8f806a;
  --accent:#ff7a18; --accent-ink:#180c02; --accent-soft:rgba(255,122,24,.14);
  --ok:#63c08e; --ok-soft:rgba(99,192,142,.13);
  --warn:#dfa648; --warn-soft:rgba(223,166,72,.13);
  --danger:#e37066; --danger-soft:rgba(227,112,102,.13);
  --focus:rgba(255,122,24,.6);
  --shadow:0 18px 42px -22px rgba(0,0,0,.82),inset 0 1px 0 rgba(255,235,210,.05);
}
@keyframes fade{from{opacity:0}to{opacity:1}}
#view-play h1, #view-play h2, #view-play h3{margin:0;font-weight:600;color:var(--ink)}
#view-play .i{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}
#view-play .i.sm{width:14px;height:14px}
#view-play .i.xs{width:13px;height:13px}
#view-play .i.xxs{width:12px;height:12px}
#view-play .i.ph{width:15px;height:15px;opacity:.45}
#view-play .bl{white-space:nowrap}
#view-play .view-inner.is-entering{animation:fade .16s linear both}
#view-play .workspace{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(320px,.95fr);gap:18px;align-items:start;margin-top:22px}
#view-play .ws-col{display:grid;gap:18px;min-width:0}
@media (max-width:980px){#view-play .workspace{grid-template-columns:minmax(0,1fr)}}
#view-play .panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);color:var(--ink)}
#view-play .panel:hover{border-color:var(--line-2);transform:none}
#view-play .head{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:46px;padding:10px 16px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,rgba(255,255,255,.025),transparent);color:var(--ink)}
#view-play .head-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
#view-play .head h2{display:flex;align-items:center;gap:9px;font-size:11.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--ink)}
#view-play .head h2 .i{width:15px;height:15px;color:var(--accent)}
#view-play .head small{color:var(--ink-2);font-size:11.5px}
#view-play .body{padding:16px;color:var(--ink)}
#view-play .counter{min-width:24px;height:22px;padding:0 8px;border:1px solid var(--line-2);border-radius:999px;background:var(--surface-2);color:var(--ink-2);font-size:11px;font-weight:700;display:inline-flex;align-items:center;justify-content:center;font-variant-numeric:tabular-nums}
#view-play .hint{color:var(--ink-2);font-size:12.5px;padding:10px 0}
#view-play .hint:empty{display:none}
#view-play .status-line{min-height:20px;padding:9px 0 0;font-size:12px;color:var(--ink-2)}
#view-play .alert{border:1px solid var(--danger);border-left-width:3px;border-radius:var(--r-sm);background:var(--danger-soft);color:var(--danger);padding:11px 13px;font-size:12.5px;margin-bottom:14px}
#view-play .session-name{font-size:18px;font-weight:700;line-height:1.3;letter-spacing:-.02em;color:var(--ink)}
#view-play .session-state{display:flex;align-items:center;gap:6px;color:var(--ink-2);font-size:12.5px;margin-top:3px}
#view-play .session-actions{display:flex;gap:8px;flex:none;width:100%}
#view-play .session-actions .btn{flex:1}
#view-play .stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px;background:transparent;border:0}
#view-play .stat{padding:11px 13px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--surface-2);color:var(--ink)}
#view-play .stat small{display:block;color:var(--ink-2);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;font-weight:600}
#view-play .stat strong{display:block;margin-top:4px;font-size:16px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--ink)}
#view-play .session-note{margin-top:12px;padding:10px 12px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:var(--r-sm);background:var(--surface-2);font-size:12.5px;color:var(--ink-2)}
#view-play .badge{flex:none;padding:3px 9px;border:1px solid rgba(99,192,142,.35);border-radius:999px;background:var(--ok-soft);color:var(--ok);font-size:10.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
#view-play .badge.warn{border-color:var(--warn);background:var(--warn-soft);color:var(--warn)}
#view-play .badge.run{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
#view-play .badge.sub{border-color:var(--line-2);background:var(--surface-2);color:var(--ink-2);text-transform:none;letter-spacing:.01em;font-weight:600}
#view-play .badge.quest{border-color:var(--accent);background:var(--accent-soft);color:var(--accent);text-transform:none;letter-spacing:.01em;font-weight:650}
#view-play .btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:34px;padding:0 13px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--surface-2);color:var(--ink);font-size:12.5px;font-weight:600}
#view-play .btn:hover:not(:disabled){background:var(--surface-3);border-color:var(--line-2)}
#view-play .btn:active:not(:disabled){background:var(--line)}
#view-play .btn.primary{background:var(--accent);border-color:transparent;color:var(--accent-ink)}
#view-play .btn.primary:hover:not(:disabled){filter:brightness(1.07)}
#view-play .btn.danger{background:var(--danger-soft);border-color:transparent;color:var(--danger)}
#view-play .btn.danger:hover:not(:disabled){filter:brightness(1.1)}
#view-play .btn.ghost{background:transparent;border-color:transparent;color:var(--ink-2)}
#view-play .btn.ghost:hover:not(:disabled){color:var(--ink);background:var(--surface-2)}
#view-play .btn.small{min-height:28px;padding:0 10px;font-size:12px;border-radius:6px}
#view-play .btn.wide{width:100%}
#view-play input, #view-play select{height:36px;padding:0 11px;border:1px solid var(--line-2);border-radius:var(--r-sm);background:var(--bg);color:var(--ink);transition:border-color .14s linear,box-shadow .14s linear}
#view-play input::placeholder{color:var(--ink-3)}
#view-play input:focus, #view-play select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
#view-play .library{display:grid;gap:8px;background:transparent;border:0}
#view-play .game{display:flex;flex-wrap:wrap;align-items:center;gap:10px 12px;padding:12px 14px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--surface-2);color:var(--ink);transition:background .14s linear,border-color .14s linear}
#view-play .game:hover{background:var(--surface-3);border-color:var(--line-2)}
#view-play .game.active{background:var(--accent-soft);border-color:var(--accent);box-shadow:inset 3px 0 0 var(--accent)}
#view-play .icon-box{width:38px;height:38px;flex:none;display:grid;place-items:center;overflow:hidden;border:1px solid var(--line-2);border-radius:9px;background:var(--surface)}
#view-play .icon-box img{width:100%;height:100%;object-fit:cover}
#view-play .game-info{flex:1 1 210px;min-width:0}
#view-play .game-title-row{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
#view-play .game-name{font-size:14px;font-weight:700;color:var(--ink);overflow-wrap:anywhere}
#view-play .game-meta{color:var(--ink-2);font-size:11.5px;margin-top:3px;overflow-wrap:anywhere}
#view-play .game-tags{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:6px}
#view-play .reason{font-size:12px;color:var(--warn);padding:9px 11px;flex:1 1 100%;border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:var(--r-sm);background:var(--surface)}
#view-play .game-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end;margin-left:auto}
#view-play .exe-row{display:flex;gap:8px;flex:1 1 100%;padding-top:4px}
#view-play .exe-row input{flex:1;min-width:0;height:32px}
#view-play .icon-picker{display:none}
#view-play .empty{padding:18px 14px;border:1px dashed var(--line-2);border-radius:var(--r-sm);color:var(--ink-3);font-size:12.5px;text-align:center;background:var(--surface-2)}
#view-play .pulse{height:44px;border-radius:var(--r-sm);background:var(--surface-2)}
#view-play .search-row{display:flex;gap:8px}
#view-play .search-row input{flex:1}
#view-play .result-area{min-height:96px;padding-top:8px}
#view-play .results{display:grid;gap:6px;max-height:340px;overflow:auto;padding-right:2px}
#view-play .result{display:flex;align-items:center;gap:12px;width:100%;text-align:left;padding:10px 12px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--surface-2);transition:background .14s linear,border-color .14s linear}
#view-play .result:hover{background:var(--surface-3);border-color:var(--line-2)}
#view-play .result[aria-pressed=true]{border-color:var(--accent);background:var(--accent-soft)}
#view-play .result-body{flex:1;min-width:0}
#view-play .result .name{font-size:13.5px;font-weight:600;overflow-wrap:anywhere}
#view-play .result .meta{color:var(--ink-3);font-size:11.5px;margin-top:2px;overflow-wrap:anywhere}
#view-play .check{width:20px;height:20px;flex:none;display:grid;place-items:center;border:1px solid var(--line-2);border-radius:6px;background:var(--surface)}
#view-play .check .i{width:12px;height:12px;color:var(--accent-ink);opacity:0}
#view-play .result[aria-pressed=true] .check{background:var(--accent);border-color:var(--accent)}
#view-play .result[aria-pressed=true] .check .i{opacity:1}
#view-play .footer-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}
#view-play .sel-label{flex:1;min-width:0;font-size:12.5px;color:var(--ink-3);overflow-wrap:anywhere}
#view-play .quest-list{display:grid;gap:8px}
#view-play .quest-card{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--surface-2)}
#view-play .quest-card.enrolled{border-color:var(--accent);background:var(--accent-soft)}
#view-play .quest-card.completed{border-color:rgba(99,192,142,.35);background:var(--ok-soft)}
#view-play .quest-main{min-width:0;flex:1}
#view-play .quest-title{font-size:13px;font-weight:650;color:var(--ink);overflow-wrap:anywhere}
#view-play .quest-sub{font-size:11.5px;color:var(--ink-3);margin-top:2px;overflow-wrap:anywhere}
#view-play .quest-bar{height:4px;border-radius:999px;background:var(--line);margin-top:7px;overflow:hidden}
#view-play .quest-bar>span{display:block;height:100%;background:var(--accent);border-radius:999px}
#view-play .quest-card.completed .quest-bar>span{background:var(--ok)}
#view-play .queue-settings{display:flex;align-items:center;gap:8px;color:var(--ink-2);font-size:12.5px;margin-bottom:12px}
#view-play .queue-settings input{width:76px;height:32px}
#view-play .queue{list-style:none;margin:0 0 12px;padding:0;display:grid;gap:7px;min-height:28px}
#view-play .queue-item{display:flex;align-items:center;gap:9px;padding:8px 10px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--surface-2);font-size:12.5px;cursor:grab;position:relative;overflow:hidden;transition:background .14s linear,border-color .14s linear,box-shadow .14s linear,opacity .14s linear}
#view-play .queue-item.dragging{opacity:.5;border-style:dashed}
#view-play .queue-item.drop-before{box-shadow:0 -2px 0 0 var(--accent)}
#view-play .queue-item.drop-after{box-shadow:0 2px 0 0 var(--accent)}
#view-play .queue-item.current{border-color:var(--accent);background:var(--accent-soft)}
#view-play .q-grip{width:8px;height:12px;flex:none;opacity:.4;background-image:radial-gradient(circle,currentColor 1px,transparent 1.15px);background-size:4px 4px;background-position:1px 1px;background-repeat:repeat}
#view-play .q-num{flex:none;min-width:18px;text-align:center;font-size:11px;font-weight:700;color:var(--ink-3);font-variant-numeric:tabular-nums}
#view-play .queue-item.current .q-num{color:var(--accent)}
#view-play .q-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:550}
#view-play .q-min{color:var(--ink-3);font-size:11px;flex:none;font-variant-numeric:tabular-nums}
#view-play .q-order{display:grid;flex:none}
#view-play .q-move, #view-play .q-del{border:0;background:transparent;color:var(--ink-3);display:grid;place-items:center;padding:2px 4px;border-radius:4px;line-height:1}
#view-play .q-del{padding:3px 5px}
#view-play .q-move:hover:not(:disabled), #view-play .q-del:hover:not(:disabled){color:var(--ink);background:var(--surface-3)}
#view-play .q-del:hover:not(:disabled){color:var(--danger)}
#view-play .q-bar{position:absolute;left:0;bottom:0;height:2px;width:0;background:var(--accent);transition:width .9s linear}
#view-play .queue-actions{display:flex;gap:8px}
#view-play .queue-actions .btn{flex:1}
#view-play .queue-status{min-height:18px;margin-top:10px;font-size:12px;color:var(--ink-3)}
.modal-scrim{position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:20px;background:rgba(10,12,16,.62);backdrop-filter:blur(8px);opacity:0;transition:opacity .18s var(--ease)}
.modal-scrim.is-open{opacity:1}
.modal{width:min(440px,100%);padding:22px 24px;border-radius:var(--r-lg);border:1px solid var(--line-2);background:var(--surface,#14181d);color:var(--ink);box-shadow:0 28px 70px -20px rgba(0,0,0,.85)}
</style>
<script>(function(){try{const t=localStorage.getItem('worthlesstask.theme');document.documentElement.setAttribute('data-theme',t==='light'?'light':'dark')}catch(_){document.documentElement.setAttribute('data-theme','dark')}})();</script></head><body>
<svg class="icon-set" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg"><defs>
<symbol id="ic-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<circle cx="12" cy="12" r="4.1"/>
<path d="M12 2.8v2.3M12 18.9v2.3M2.8 12h2.3M18.9 12h2.3M5.4 5.4l1.6 1.6M17 17l1.6 1.6M18.6 5.4L17 7M7 17l-1.6 1.6"/>
</symbol>
<symbol id="ic-home" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M5.6 20.4V10.6L18.4 5.2v15.2"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M5.6 15.6h12.8"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M3.2 20.4h17.6"/>
</symbol>
<symbol id="ic-games" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M9.4 7.6h5.2L20 11.4l-1.4 7a1.9 1.9 0 0 1-1.9 1.5H7.3a1.9 1.9 0 0 1-1.9-1.5L4 11.4z"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M7.8 13.5h2.8M9.2 12.1v2.8"/>
<circle fill="none" stroke="currentColor" stroke-width="1.25" cx="15.2" cy="13.2" r="1.05"/>
<circle fill="none" stroke="currentColor" stroke-width="1.25" cx="17.4" cy="15.4" r="1.05"/>
</symbol>
<symbol id="ic-search" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<circle fill="none" stroke="currentColor" stroke-width="1.25" cx="10.4" cy="10.4" r="6.1"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M14.9 14.9 20.4 20.4"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M8.2 10.4h4.4"/>
</symbol>
<symbol id="ic-library" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M4.6 19.4V7.8h3.4v11.6"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M9.2 19.4V6.4h3.4v13"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M14.6 19.4 17.4 6.6l2.2.5-2.6 12.3"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M3.2 19.4h17.6"/>
</symbol>
<symbol id="ic-session" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M13.9 18.7A8.3 8.3 0 1 1 18.7 13.9"/>
<circle fill="none" stroke="currentColor" stroke-width="1.25" cx="12" cy="12" r="2.5"/>
</symbol>
<symbol id="ic-queue" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M4.2 7.4h9.6"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M7 12h9.6"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M4.2 16.6h9.6"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M18.4 5.8v12.4"/>
</symbol>
<symbol id="ic-play" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M8.4 5.6 18.6 11.6a.45.45 0 0 1 0 .8L8.4 18.4a.45.45 0 0 1-.7-.4V6a.45.45 0 0 1 .7-.4z"/>
</symbol>
<symbol id="ic-stop" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M8.6 6.6h6.8a2 2 0 0 1 2 2v6.8a2 2 0 0 1-2 2H8.6a2 2 0 0 1-2-2V8.6a2 2 0 0 1 2-2z"/>
</symbol>
<symbol id="ic-trash" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M4.6 7.4h14.8"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M9.4 7.4V5.2h5.2v2.2"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M6.6 7.4 7.5 18.6a1.5 1.5 0 0 0 1.5 1.4h6a1.5 1.5 0 0 0 1.5-1.4l.9-11.2"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M10.5 10.8v5.6M13.5 10.8v5.6"/>
</symbol>
<symbol id="ic-image" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M4.4 6.2h15.2a1.4 1.4 0 0 1 1.4 1.4v8.8a1.4 1.4 0 0 1-1.4 1.4H4.4A1.4 1.4 0 0 1 3 16.4V7.6a1.4 1.4 0 0 1 1.4-1.4z"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M3.4 16.4 9.1 11l3.9 3.5 2.7-2.3 4.9 4.6"/>
<circle fill="none" stroke="currentColor" stroke-width="1.25" cx="8.4" cy="9.6" r="1.4"/>
</symbol>
<symbol id="ic-edit" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M14.6 5.2 18.8 9.4 8.6 19.6 4.2 20.8 5.4 16.4z"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M12.8 7 17 11.2"/>
</symbol>
<symbol id="ic-plus" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M12 5.6v12.8"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M5.6 12h12.8"/>
</symbol>
<symbol id="ic-minus" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M5.6 12h12.8"/>
</symbol>
<symbol id="ic-up" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M12 18.6V5.4"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M6.3 11.1 12 5.4l5.7 5.7"/>
</symbol>
<symbol id="ic-down" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M12 5.4v13.2"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M6.3 12.9 12 18.6l5.7-5.7"/>
</symbol>
<symbol id="ic-close" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M6.5 6.5 17.5 17.5"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M17.5 6.5 6.5 17.5"/>
</symbol>
<symbol id="ic-warn" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M12 4.4 20.6 19.6H3.4z"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M12 9.6v4.3"/>
<circle fill="none" stroke="currentColor" stroke-width="1.25" cx="12" cy="17" r=".85"/>
</symbol>
<symbol id="ic-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M5.2 12.6 9.9 17.3 18.8 6.7"/>
</symbol>
<symbol id="ic-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M12.01 3.8A8.2 8.2 0 1 0 20.2 11.99A6 6 0 1 1 12.01 3.8z"/>
</symbol>
<symbol id="ic-bolt" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M13.6 3.8 6.2 12.6h5.2l-1.2 7.6 7.4-8.8h-5.2z"/>
</symbol>
<symbol id="ic-clock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<circle fill="none" stroke="currentColor" stroke-width="1.25" cx="12" cy="12" r="8.2"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M12 7.3V12l3.8 2.3"/>
</symbol>
<symbol id="ic-chip" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M8.6 6.4h6.8l2.2 2.2v6.8l-2.2 2.2H8.6l-2.2-2.2V8.6z"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M10.2 3.6v2.8M13.8 3.6v2.8M10.2 17.6v2.8M13.8 17.6v2.8M3.6 10.2h2.8M3.6 13.8h2.8M17.6 10.2h2.8M17.6 13.8h2.8"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M10.4 10.4h3.2v3.2h-3.2z"/>
</symbol>
<symbol id="ic-sync" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M20 11a8.1 8.1 0 0 0-15.5-2m-.5-4v4h4"/>
<path fill="none" stroke="currentColor" stroke-width="1.25" d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4"/>
</symbol>
</defs></svg>

<div class="ambient" aria-hidden="true"><div class="pool a"></div><div class="pool b"></div><div class="pool c"></div><div class="pool d"></div></div>
<div class="gridlines" aria-hidden="true"></div>
<div class="vignette" aria-hidden="true"></div>
<div class="grain" aria-hidden="true"></div>
<div class="shell">
<header class="nav">
  <div class="nav-left">
    <a class="brand" href="#home"><span class="mark" aria-hidden="true"><svg class="i" viewBox="0 0 24 24"><path d="M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a8.6 8.6 0 1 0 11.1 11.1z"/></svg></span><span class="brand-name">worthlesstask</span></a>
    <button class="theme" id="themeToggle" type="button" aria-pressed="false" aria-label="Switch to dark theme" title="Switch to dark theme"><svg class="i i-sun" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-sun"></use></svg><svg class="i i-moon" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-moon"></use></svg></button>
    <div class="lang" id="langSwitch" role="group" data-i18n-aria="nav.lang" aria-label="Interface language">
      <button class="lang-btn" type="button" data-lang="en" aria-pressed="true">EN</button>
      <button class="lang-btn" type="button" data-lang="ru" aria-pressed="false">RU</button>
    </div>
  </div>
  <nav class="tabs" id="navTabs" role="tablist" data-i18n-aria="nav.tabs" aria-label="Sections">
    <span class="tab-indicator" id="tabIndicator" aria-hidden="true"></span>
    <button class="tab" id="tabHome" role="tab" aria-selected="true" aria-controls="view-home" data-view="home" tabindex="0"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.6 10.6 12 4l8.4 6.6V19a1.2 1.2 0 0 1-1.2 1.2H4.8A1.2 1.2 0 0 1 3.6 19z"/><path d="M9.7 20.2v-5.5h4.6v5.5"/></svg><span data-i18n="tab.home">Home</span></button>
    <button class="tab" id="tabPlay" role="tab" aria-selected="false" aria-controls="view-play" data-view="play" tabindex="-1"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M7.4 8.6h9.2a4.2 4.2 0 0 1 4.1 3.3l.6 2.7a2.9 2.9 0 0 1-5.2 2.1L14.8 15H9.2L7.9 16.7a2.9 2.9 0 0 1-5.2-2.1l.6-2.7a4.2 4.2 0 0 1 4.1-3.3z"/><path d="M8.6 11.3h2.4M9.8 10.1v2.4"/><circle cx="16.3" cy="11.7" r=".95"/><circle cx="18" cy="13.4" r=".95"/></svg><span data-i18n="tab.play">Games</span></button>
  </nav>
  <div class="nav-right">
    <div class="chip">
      <span id="connectionDot" class="dot off"></span>
      <span id="connectionText" data-i18n="status.connecting">Connecting to the panel</span>
    </div>
  </div>
</header>
<main>
<section id="view-home" class="view" role="tabpanel" aria-labelledby="tabHome" tabindex="-1">
  <div class="view-inner">
    <div class="hero-stage">
      <div class="hero-meta"><span class="eyebrow" data-i18n="home.eyebrow">DISCORD PRESENCE &amp; QUEST BYPASS · 2026</span></div>
      <h1><span class="hero-word">worthlesstask</span><span class="hero-sub" data-i18n="home.sub">PLAYING, VERIFIED.</span></h1>
      <p class="lede" data-i18n="home.lede">Launch lightweight verified processes, bind Discord Rich Presence, and complete Orbs quests without downloading full games.</p>
      <div class="hero-actions">
        <button class="btn primary" type="button" data-goto="play" data-i18n="home.cta">Open the game space</button>
        <button class="btn" type="button" data-goto="play" data-focus="query" data-i18n="home.cta2">Find a game</button>
      </div>
      <div class="moon-scene" aria-hidden="true">
        <svg class="moon-svg" viewBox="0 0 400 400" role="presentation">
          <defs>
            <radialGradient id="mnSurf" cx="33%" cy="27%" r="80%">
              <stop offset="0" stop-color="#fdfefe"/><stop offset=".34" stop-color="#e2e7ec"/><stop offset=".66" stop-color="#b3bac3"/><stop offset=".88" stop-color="#7f8791"/><stop offset="1" stop-color="#5d646e"/>
            </radialGradient>
            <radialGradient id="mnShade" cx="74%" cy="78%" r="76%">
              <stop offset="0" stop-color="#04060a" stop-opacity=".66"/><stop offset=".5" stop-color="#04060a" stop-opacity=".22"/><stop offset="1" stop-color="#04060a" stop-opacity="0"/>
            </radialGradient>
            <radialGradient id="mnGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0" stop-color="#f2f6fb" stop-opacity=".30"/><stop offset=".45" stop-color="#dbe4ee" stop-opacity=".12"/><stop offset="1" stop-color="#dbe4ee" stop-opacity="0"/>
            </radialGradient>
            <linearGradient id="mnRim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity=".55"/><stop offset=".6" stop-color="#ffffff" stop-opacity=".06"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>
            <filter id="mnSoft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="6"/></filter>
            <filter id="mnGlowB" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="20"/></filter>
            <filter id="mnGrain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="4" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>
            <clipPath id="mnClip"><circle cx="200" cy="200" r="122"/></clipPath>
          </defs>
          <circle cx="200" cy="200" r="172" fill="url(#mnGlow)" filter="url(#mnGlowB)"/>
          <g class="mn-orbit"><ellipse cx="200" cy="200" rx="182" ry="66" transform="rotate(-18 200 200)"/></g>
          <g class="mn-stars">
            <circle cx="52" cy="96" r="1.8"/><circle cx="348" cy="72" r="1.5"/><circle cx="72" cy="316" r="1.4"/><circle cx="336" cy="330" r="1.9"/><circle cx="196" cy="34" r="1.3"/><circle cx="30" cy="196" r="1.2"/><circle cx="372" cy="206" r="1.4"/><circle cx="150" cy="366" r="1.2"/>
          </g>
          <circle cx="200" cy="200" r="122" fill="url(#mnSurf)"/>
          <g clip-path="url(#mnClip)">
            <g filter="url(#mnSoft)" opacity=".34" fill="#79808b">
              <ellipse cx="164" cy="152" rx="46" ry="33" transform="rotate(-20 164 152)"/>
              <ellipse cx="248" cy="238" rx="52" ry="30" transform="rotate(24 248 238)"/>
              <ellipse cx="150" cy="262" rx="26" ry="38" transform="rotate(36 150 262)"/>
              <ellipse cx="264" cy="140" rx="22" ry="16" transform="rotate(-12 264 140)"/>
            </g>
            <g class="mn-craters">
              <circle cx="152" cy="182" r="19"/><circle cx="152" cy="182" r="19" class="rim"/>
              <circle cx="238" cy="166" r="11"/><circle cx="238" cy="166" r="11" class="rim"/>
              <circle cx="196" cy="252" r="15"/><circle cx="196" cy="252" r="15" class="rim"/>
              <circle cx="286" cy="216" r="8"/><circle cx="286" cy="216" r="8" class="rim"/>
              <circle cx="122" cy="228" r="7"/><circle cx="122" cy="228" r="7" class="rim"/>
              <circle cx="216" cy="118" r="6"/><circle cx="216" cy="118" r="6" class="rim"/>
            </g>
            <rect x="78" y="78" width="244" height="244" filter="url(#mnGrain)" opacity=".13"/>
            <circle cx="200" cy="200" r="122" fill="url(#mnShade)"/>
          </g>
          <circle cx="200" cy="200" r="122" fill="none" stroke="url(#mnRim)" stroke-width="1.6"/>
          <circle cx="200" cy="200" r="129" fill="none" stroke="rgba(255,255,255,.05)" stroke-width="10"/>
        </svg>
      </div>
    </div>
    <div class="principles">
      <article class="principle">
        <span class="pr-ic"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-chip"></use></svg></span>
        <h3 data-i18n="home.p1.t">Universal bypass</h3>
        <p data-i18n="home.p1.d">Matches Discord's catalogue paths and binds Rich Presence IPC on the same PID — even for zero-executable Quest titles.</p>
      </article>
      <article class="principle">
        <span class="pr-ic"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-check"></use></svg></span>
        <h3 data-i18n="home.p2.t">Local only</h3>
        <p data-i18n="home.p2.d">Everything runs on your machine. Reads local Discord quest cache and never touches your account token.</p>
      </article>
      <article class="principle">
        <span class="pr-ic"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-bolt"></use></svg></span>
        <h3 data-i18n="home.p3.t">Verified signal</h3>
        <p data-i18n="home.p3.d">Process state, bypass strategy, and Discord RPC acknowledgement are tracked independently in real time.</p>
      </article>
    </div>

    <section class="flow">
      <div class="flow-head"><span class="flow-eyebrow" data-i18n="home.flow.title">How it works</span></div>
      <ol class="flow-steps">
        <li class="flow-step">
          <span class="fs-ic"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-sync"></use></svg></span>
          <span class="fs-t" data-i18n="home.s1.t">Sync</span>
          <span class="fs-d" data-i18n="home.s1.d">Active Discord quests and catalogue rules sync automatically on startup.</span>
        </li>
        <li class="flow-step">
          <span class="fs-ic"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-plus"></use></svg></span>
          <span class="fs-t" data-i18n="home.s2.t">Prepare</span>
          <span class="fs-d" data-i18n="home.s2.d">Lightweight worker executables are staged in exact catalogue paths.</span>
        </li>
        <li class="flow-step">
          <span class="fs-ic"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-queue"></use></svg></span>
          <span class="fs-t" data-i18n="home.s3.t">Queue</span>
          <span class="fs-d" data-i18n="home.s3.d">Set the minutes per game or run any title on demand.</span>
        </li>
        <li class="flow-step">
          <span class="fs-ic"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-play"></use></svg></span>
          <span class="fs-t" data-i18n="home.s4.t">Earn Orbs</span>
          <span class="fs-d" data-i18n="home.s4.d">Discord detects the process and IPC activity, crediting Quest progress.</span>
        </li>
      </ol>
    </section>
  </div>
</section>

<section id="view-play" class="view" role="tabpanel" aria-labelledby="tabPlay" tabindex="-1" hidden>
  <div class="view-inner">
    <div class="workspace">
      <div class="ws-col">
        <section class="panel">
          <div class="head">
            <h2><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-library"></use></svg><span data-i18n="library.title">My games</span></h2>
            <div class="head-right">
              <button id="syncQuests" class="btn small" type="button"><svg class="i xs" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-sync"></use></svg><span class="bl" data-i18n="quests.sync">Sync Discord Quests</span></button>
              <span class="counter" id="gameCount">0</span>
            </div>
          </div>
          <div class="body">
            <div id="games" class="library"></div>
            <div id="libraryEmpty" class="empty" data-i18n="library.empty">Add a game from the search results or sync active Discord quests</div>
          </div>
        </section>

        <section class="panel">
          <div class="head"><h2><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-search"></use></svg><span data-i18n="search.title">Find a game</span></h2><small data-i18n="search.note">Discord catalogue</small></div>
          <div class="body">
            <form id="searchForm" class="search-row">
              <input id="query" type="search" data-i18n-aria="search.aria" aria-label="Game name" data-i18n-ph="search.placeholder" placeholder="For example: EA SPORTS FC 27" maxlength="256" autocomplete="off" required>
              <button id="search" class="btn primary" type="submit"><svg class="i sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-search"></use></svg><span class="bl">Search</span></button>
            </form>
            <div id="searchStatus" class="status-line" role="status" aria-live="polite">Type a name to search</div>
            <div class="result-area">
              <div id="results" class="results"></div>
              <div id="searchEmpty" class="empty">Catalogue games will appear here</div>
            </div>
            <div class="footer-row">
              <span id="selectionLabel" class="sel-label">No game selected</span>
              <button id="addSelected" class="btn" type="button" disabled><svg class="i sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-plus"></use></svg><span class="bl">Add</span></button>
              <button id="addAndRun" class="btn primary" type="button" disabled><svg class="i sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-play"></use></svg><span class="bl">Add &amp; start</span></button>
            </div>
          </div>
        </section>
      </div>

      <div class="ws-col">
        <section class="panel">
          <div class="head"><h2><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-session"></use></svg><span data-i18n="session.title">Current session</span></h2><span id="sessionBadge" class="badge run">Pending</span></div>
          <div class="body">
            <div id="globalError" class="alert" role="alert" hidden></div>
            <div class="session-top">
              <div>
                <div id="activeName" class="session-name">Nothing running</div>
                <div id="activeState" class="session-state" role="status">Ready to start</div>
              </div>
              <div class="session-actions">
                <button id="stopAll" class="btn danger" type="button" disabled><svg class="i sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-stop"></use></svg><span class="bl" data-i18n="session.stop">Stop</span></button>
                <button id="resetSession" class="btn ghost" type="button" disabled><svg class="i sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-trash"></use></svg><span class="bl" data-i18n="session.reset">Delete session</span></button>
              </div>
            </div>
            <div class="stats">
              <div class="stat"><small data-i18n="session.uptime">Process time</small><strong id="elapsed">00:00</strong></div>
              <div class="stat"><small data-i18n="session.pid">PID</small><strong id="pid">—</strong></div>
            </div>
            <div id="sessionNote" class="session-note" hidden></div>
          </div>
        </section>

        <section class="panel">
          <div class="head"><h2><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-bolt"></use></svg><span data-i18n="quests.title">Discord Quests</span></h2><span class="counter" id="questCount">0</span></div>
          <div class="body">
            <div id="questList" class="quest-list"></div>
            <div id="questEmpty" class="empty" data-i18n="quests.empty">No active desktop quests found in local Discord cache</div>
          </div>
        </section>

        <section class="panel">
          <div class="head"><h2><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-queue"></use></svg><span data-i18n="queue.title">Game queue</span></h2><span class="counter" id="queueCount">0</span></div>
          <div class="body">
            <label class="queue-settings"><span data-i18n="queue.per">Minutes per game</span><input id="queueMinutes" type="number" value="15" min="1" max="1440" step="1" data-i18n-aria="queue.aria" aria-label="Minutes per game"><span data-i18n="queue.unit">min</span></label>
            <ol id="queue" class="queue"></ol>
            <div id="queueEmpty" class="hint" data-i18n="queue.empty">Nothing queued yet</div>
            <div class="queue-actions">
              <button id="startQueue" class="btn primary" type="button" disabled><svg class="i sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-play"></use></svg><span class="bl" data-i18n="queue.start">Start</span></button>
              <button id="clearQueue" class="btn ghost" type="button" disabled><svg class="i sm" viewBox="0 0 24 24" aria-hidden="true"><use href="#ic-close"></use></svg><span class="bl" data-i18n="queue.clear">Clear</span></button>
            </div>
            <div id="queueStatus" class="queue-status">Queue stopped</div>
          </div>
        </section>
      </div>
    </div>
  </div>
</section>
</main>
</div>
<div id="toast" class="toast glass-float" role="status" hidden></div>
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
</div>
<script>
'use strict';
const $ = id => document.getElementById(id);
const SVGNS='http://www.w3.org/2000/svg';
const I18N={
en:{
"nav.lang":"Interface language","nav.tabs":"Sections","tab.home":"Home","tab.play":"Games",
"home.eyebrow":"DISCORD PRESENCE & QUEST BYPASS · 2026","home.sub":"PLAYING, VERIFIED.",
"home.lede":"Launch lightweight verified processes, bind Discord Rich Presence, and complete Orbs quests without downloading full games.",
"home.cta":"Open the game space","home.cta2":"Find a game","home.instrument":"Summary",
"home.p1.t":"Universal bypass","home.p1.d":"Matches Discord's catalogue paths and binds Rich Presence IPC on the same PID — even for zero-executable Quest titles.",
"home.p2.t":"Local only","home.p2.d":"Everything runs on your machine. Reads local Discord quest cache and never touches your account token.",
"home.p3.t":"Verified signal","home.p3.d":"Process state, bypass strategy, and Discord RPC acknowledgement are tracked independently in real time.",
"home.flow.title":"How it works",
"home.s1.t":"Sync","home.s1.d":"Active Discord quests and catalogue rules sync automatically on startup.",
"home.s2.t":"Prepare","home.s2.d":"Lightweight worker executables are staged in exact catalogue paths.",
"home.s3.t":"Queue","home.s3.d":"Set the minutes per game or run any title on demand.",
"home.s4.t":"Earn Orbs","home.s4.d":"Discord detects the process and IPC activity, crediting Quest progress.",
"search.title":"Find a game","search.note":"Discord catalogue","search.placeholder":"For example: EA SPORTS FC 27","search.aria":"Game name",
"search.submit":"Search","search.busy":"Searching…",
"library.title":"My games","library.empty":"Add a game from the search results or sync active Discord quests","library.unit":"games","library.icon":"Icon",
"library.queueAdd":"Add to queue","library.queueRemove":"Remove from queue","library.delete":"Delete",
"library.exeName":"EXE name","library.makeExe":"Create EXE","library.save":"Save",
"library.exePlaceholder":"for example fc26.exe","library.exeAria":"Game file name",
"library.start":"Start","library.starting":"Starting…","library.running":"Running",
"badge.session":"Session","badge.noExe":"No EXE","badge.outside":"Custom EXE","badge.ready":"EXE ready","badge.missing":"EXE not built","meta.noExe":"EXE not set",
"bypass.native_exe":"Catalogue EXE","bypass.subdir_exe":"Subfolder EXE","bypass.catalogue_exe":"Catalogue EXE",
"bypass.carrier_ipc_sku":"Carrier + IPC + SKU","bypass.carrier_ipc":"Carrier + IPC","bypass.quest_sibling_ipc":"Quest Sibling + IPC","bypass.manual":"Manual EXE",
"quests.title":"Discord Quests","quests.sync":"Sync Quests & Bypass","quests.syncing":"Syncing…",
"quests.empty":"No active desktop quests found in local Discord cache","quests.enrolled":"Enrolled","quests.completed":"Completed","quests.available":"Available in Discord",
"quests.orbs":"Orbs","quests.synced":"Discord quests and bypasses synced ({n} updated)",
"session.title":"Current session","session.uptime":"Process time","session.pid":"PID","session.stop":"Stop","session.reset":"Delete session",
"queue.title":"Game queue","queue.per":"Minutes per game","queue.unit":"min","queue.aria":"Minutes per game","queue.empty":"Nothing queued yet",
"queue.start":"Start","queue.restart":"Restart","queue.clear":"Clear","queue.of":"of","queue.running":"Queue running","queue.stopped":"Queue stopped",
"selection.none":"No game selected","add":"Add","add.busy":"Adding…","add.exists":"Already in library","addRun":"Add & start",
"status.connected":"Panel connected","status.offline":"No connection to the panel","dlg.ok":"OK","dlg.cancel":"Cancel","dlg.delete":"Delete","dlg.end":"End","dlg.delTitle":"Delete game?","dlg.delMsg":"The game will be removed from the library. Installed game files are not affected.","dlg.deleted":"Game removed from the library","dlg.resetTitle":"End session?","dlg.resetMsg":"End the session and clear its record?",
"search.loading":"Loading results…","search.none":"No matches","search.found":"Found: {n}. Select an entry.",
"active.idle":"Nothing running","rpc.connected":"RPC confirmed by Discord","rpc.connecting":"Connecting to Discord…",
"rpc.reconnecting":"Waiting / reconnecting","rpc.error":"RPC error","active.prepare":"Preparing and starting the process…","active.stopping":"Stopping the process…",
"active.ready":"Ready to start","active.unconfirmed":"RPC not confirmed yet",
"queue.unitShort":"min",
"err.exe.missing":"EXE not found",
"err.busy.operation":"Wait for the current start or stop to finish",
"err.busy.other":"Another operation is still running. Wait for it to finish.",
"err.session.active":"Stop the active session first",
"err.exe.unavailable":"The catalogue has no executable for this game. Automatic start is unavailable.",
"err.queue.too_long":"The queue must hold at most 100 games",
"err.queue.minutes":"Enter a whole number of minutes between 1 and 1440",
"err.game.missing":"Game not found",
"err.icon.too_large":"The icon must be 2 MiB or smaller",
"err.icon.format":"Unsupported icon format: ICO, PNG, JPG, BMP or WebP",
"err.slug.invalid":"Invalid game identifier",
"err.search.too_long":"The search query must be 256 characters or fewer",
"err.game.name_length":"Enter a game name of up to 256 characters",
"err.game.bad_id":"Invalid Application ID",
"err.game.stale":"That entry is out of date. Search again.",
"err.game.invalid":"Check the game's settings",
"err.exe.bad_name":"Expected an .exe name with no path or shell characters",
"err.exe.build_failed":"Could not build the EXE",
"err.queue.not_list":"The queue must be a list of games",
"err.library.save_failed":"Could not save the library",
"err.library.load_failed":"Could not read the library",
"err.request.origin":"Only requests from the local panel are allowed",
"err.request.size":"Invalid request size (4 MiB maximum)",
"err.request.streaming":"Streamed request bodies are not supported",
"err.request.truncated":"Request body arrived incomplete",
"err.request.json":"Malformed request JSON",
"err.request.object":"The request body must be a JSON object",
"err.server.internal":"Internal error. See the application log for details.",
"err.exe.bad_type":"The file name must be a string","err.icon.missing":"No icon uploaded","err.http.not_found":"Not found",
"err.request.local_only":"The panel accepts requests from 127.0.0.1 only","err.server.no_port":"No free local port",
"err.process.stop_failed":"Could not open the process to stop it",
"err.rpc.unconfirmed":"The process is running, but Discord has not confirmed the RPC yet. Check the desktop Discord.",
"err.game.bad_id_length":"The Application ID must be 17–20 digits",
"err.app.missing":"The application folder or the library file was not found",
"err.exe.not_windows":"The prepared file is not a Windows EXE",
"err.library.bad_shape":"Expected a list of games","err.library.bad_id":"Invalid identifier in the library",
"err.icon.not_in_folder":"The icon must live in the icons folder","err.icon.empty":"Choose a non-empty icon of up to 2 MiB",
"err.exe.symlink_instead":"A symbolic link cannot be used instead of the EXE",
"err.process.exited":"The process exited unexpectedly. See the application log for details.",
"err.queue.stopped":"The queue stopped. See the application log for details.",
"err.exe.symlink_blocked":"The EXE cannot be written through a symbolic link",
"err.exe.foreign_file":"That file already exists and does not belong to worthlesstask",
"net.aborted":"The request was cancelled or timed out",
"net.offline":"No connection to the local program. Check that worthlesstask is running.",
"http.generic":"Request failed: ",
"theme.toDark":"Switch to dark theme","theme.toLight":"Switch to light theme","status.connecting":"Connecting to the panel","session.pending":"Pending","session.processing":"Processing","session.process":"Process","session.external":"Started manually","session.connectedShort":"Connected",
"session.multi":"Several game windows are running ({n}). Discord shows the last one. Press Stop to close them all.",
"session.externalNote":"The game was started manually — by the file next to the program. You can stop it here.",
"session.lastAck":"Last acknowledgement: ",
"session.ackWait":"The process exists. Waiting for an RPC answer; this is not an activity confirmation yet.",
"session.noteIdle":"The process launch and the RPC acknowledgement are shown separately.",
"queue.dragHint":"Drag to reorder","queue.up":"Up","queue.down":"Down","queue.remove":"Remove from queue",
"search.emptyNone":"No matches. Try the full or original name.",
"search.noFile":"No direct EXE in catalogue — Carrier + IPC bypass will be configured automatically",
"search.error":"Search failed","search.changedHint":"Press Search for a new query","search.changed":"Query changed",
"search.initial":"Type a name to search","search.idle":"Catalogue games will appear here",
"notify.added":"Game added, bypass EXE prepared","notify.addedRun":"Game added, start requested","notify.exeSaved":"EXE name saved",
"notify.startRequested":"Start request accepted",
"notify.prepareDone":"EXE created. The file sits in the workers folder — double-click it or press Start to open the game window.",
"notify.iconTooLarge":"The icon must be 2 MiB or smaller","notify.iconSaved":"Icon saved. It applies to the window at the next start.",
"notify.stopRequested":"Stop request accepted","notify.sessionDeleted":"Session deleted","notify.queueCleared":"Queue cleared","notify.queueStarted":"Queue started",
"card.fileTip":"File: {p}\nDouble-click it or press Start to open the game window.","card.processTip":"Process name: ","card.exeFailed":"Could not build the EXE: ",
"reason.no_exe":"No EXE set. Enter the file name or press Sync Quests & Bypass.",
"reason.manual":"The EXE name was entered manually. Ensure it matches a catalogue process or use Sync Quests & Bypass.",
"reason.derived":"Discord lists no direct file for this game. Press Sync Quests & Bypass to attach an automatic carrier executable."
},
ru:{
"nav.lang":"Язык интерфейса","nav.tabs":"Разделы","tab.home":"Главная","tab.play":"Игры",
"home.eyebrow":"СИСТЕМА ОБХОДА И КВЕСТОВ DISCORD · 2026","home.sub":"ИГРАЕТ. ПОДТВЕРЖДЕНО.",
"home.lede":"Запускайте лёгкие проверенные процессы, привязывайте Discord Rich Presence и выполняйте квесты на Орбы без скачивания полных игр.",
"home.cta":"Открыть панель игр","home.cta2":"Найти игру","home.instrument":"Сводка",
"home.p1.t":"Универсальный обход","home.p1.d":"Подбирает точный путь процесса из каталога Discord и связывает IPC Rich Presence по PID — даже для игр без исполняемых файлов.",
"home.p2.t":"Только локально","home.p2.d":"Всё работает на вашем компьютере. Читает локальный кэш квестов Discord и не трогает токен аккаунта.",
"home.p3.t":"Проверенный сигнал","home.p3.d":"Статус процесса, режим обхода и подтверждение RPC от Discord отслеживаются отдельно в реальном времени.",
"home.flow.title":"Как это работает",
"home.s1.t":"Синхронизация","home.s1.d":"Активные квесты Discord и правила обхода обновляются автоматически при запуске.",
"home.s2.t":"Подготовка","home.s2.d":"Лёгкие исполняемые файлы создаются по точным путям каталога Discord.",
"home.s3.t":"Очередь","home.s3.d":"Задайте таймер в минутах на каждую игру или запускайте любую вручную.",
"home.s4.t":"Зачёт Орбов","home.s4.d":"Discord видит процесс и IPC-активность, начисляя прогресс задания.",
"search.title":"Найти игру","search.note":"каталог Discord","search.placeholder":"Например: EA SPORTS FC 27","search.aria":"Название игры",
"search.submit":"Найти","search.busy":"Поиск…",
"library.title":"Мои игры","library.empty":"Добавьте игру через поиск или синхронизируйте активные квесты Discord","library.unit":"игр","library.icon":"Иконка",
"library.queueAdd":"В очередь","library.queueRemove":"Убрать из очереди","library.delete":"Удалить",
"library.exeName":"Имя EXE","library.makeExe":"Создать EXE","library.save":"Сохранить",
"library.exePlaceholder":"например fc26.exe","library.exeAria":"Имя файла игры",
"library.start":"Запустить","library.starting":"Запуск…","library.running":"Запущено",
"badge.session":"Сессия","badge.noExe":"Нет EXE","badge.outside":"Свой EXE","badge.ready":"EXE готов","badge.missing":"EXE не создан","meta.noExe":"EXE не указан",
"bypass.native_exe":"EXE каталога","bypass.subdir_exe":"Папка + EXE","bypass.catalogue_exe":"EXE каталога",
"bypass.carrier_ipc_sku":"Carrier + IPC + SKU","bypass.carrier_ipc":"Carrier + IPC","bypass.quest_sibling_ipc":"Quest Sibling + IPC","bypass.manual":"Ручной EXE",
"quests.title":"Квесты Discord","quests.sync":"Синхронизировать квесты","quests.syncing":"Синхронизация…",
"quests.empty":"В локальном кэше Discord пока нет активных заданий для ПК","quests.enrolled":"Принято","quests.completed":"Завершено","quests.available":"Доступно в Discord",
"quests.orbs":"Орбов","quests.synced":"Квесты и обходы синхронизированы (обновлено: {n})",
"session.title":"Текущая сессия","session.uptime":"Время процесса","session.pid":"PID","session.stop":"Остановить","session.reset":"Удалить сессию",
"queue.title":"Очередь игр","queue.per":"На каждую игру","queue.unit":"мин","queue.aria":"Минут на игру","queue.empty":"Очередь пуста",
"queue.start":"Запустить","queue.restart":"Перезапустить","queue.clear":"Очистить","queue.of":"из","queue.running":"Очередь работает","queue.stopped":"Очередь остановлена",
"selection.none":"Игра не выбрана","add":"Добавить","add.busy":"Добавление…","add.exists":"Уже в библиотеке","addRun":"Добавить и запустить",
"status.connected":"Панель подключена","status.offline":"Нет связи с панелью","dlg.ok":"ОК","dlg.cancel":"Отмена","dlg.delete":"Удалить","dlg.end":"Завершить","dlg.delTitle":"Удалить игру?","dlg.delMsg":"Игра будет удалена из библиотеки. Файлы установленной игры не затрагиваются.","dlg.deleted":"Игра удалена из библиотеки","dlg.resetTitle":"Завершить сессию?","dlg.resetMsg":"Завершить сессию и очистить запись о ней?",
"search.loading":"Загружаем результаты…","search.none":"Совпадений нет","search.found":"Найдено: {n}. Выберите запись.",
"active.idle":"Ничего не запущено","rpc.connected":"RPC подтверждён Discord","rpc.connecting":"Подключение к Discord…",
"rpc.reconnecting":"Ожидание / переподключение","rpc.error":"Ошибка RPC","active.prepare":"Подготовка и запуск процесса…","active.stopping":"Остановка процесса…",
"active.ready":"Готово к запуску","active.unconfirmed":"RPC ещё не подтверждён",
"queue.unitShort":"мин",
"err.exe.missing":"EXE не найден",
"err.busy.operation":"Дождитесь завершения запуска или остановки",
"err.busy.other":"Другая операция ещё выполняется. Дождитесь её завершения.",
"err.session.active":"Сначала остановите активную сессию",
"err.exe.unavailable":"В каталоге нет исполняемого файла для этой игры. Автоматический запуск недоступен.",
"err.queue.too_long":"Очередь должна содержать не более 100 игр",
"err.queue.minutes":"Укажите целое число минут от 1 до 1440",
"err.game.missing":"Игра не найдена",
"err.icon.too_large":"Иконка должна быть не больше 2 МиБ",
"err.icon.format":"Формат файла не поддерживается: используйте ICO, PNG, JPG, BMP или WebP",
"err.slug.invalid":"Некорректный идентификатор игры",
"err.search.too_long":"Поисковый запрос должен быть не длиннее 256 символов",
"err.game.name_length":"Укажите название игры до 256 символов",
"err.game.bad_id":"Некорректный Application ID",
"err.game.stale":"Выбранная карточка устарела. Повторите поиск.",
"err.game.invalid":"Проверьте параметры игры",
"err.exe.bad_name":"Ожидается имя .exe без пути и служебных символов",
"err.exe.build_failed":"Не удалось создать EXE",
"err.queue.not_list":"Очередь должна быть списком игр",
"err.library.save_failed":"Не удалось сохранить библиотеку",
"err.library.load_failed":"Не удалось прочитать библиотеку",
"err.request.origin":"Разрешены только запросы из локальной панели",
"err.request.size":"Некорректный размер запроса (максимум 4 МиБ)",
"err.request.streaming":"Потоковая передача запроса не поддерживается",
"err.request.truncated":"Запрос получен не полностью",
"err.request.json":"Некорректный JSON запроса",
"err.request.object":"Тело запроса должно быть JSON-объектом",
"err.server.internal":"Внутренняя ошибка. Подробности в журнале приложения.",
"err.exe.bad_type":"Имя файла должно быть строкой","err.icon.missing":"Иконка не загружена","err.http.not_found":"Не найдено",
"err.request.local_only":"Панель принимает запросы только с 127.0.0.1","err.server.no_port":"Нет свободного локального порта",
"err.process.stop_failed":"Не удалось открыть процесс для остановки",
"err.rpc.unconfirmed":"Процесс запущен, но RPC ещё не подтверждён. Проверьте настольный клиент Discord.",
"err.game.bad_id_length":"Application ID должен содержать 17–20 цифр",
"err.app.missing":"Не найдена папка приложения или файл библиотеки",
"err.exe.not_windows":"Подготовленный файл не является Windows EXE",
"err.library.bad_shape":"Ожидался список игр","err.library.bad_id":"Недопустимый идентификатор в библиотеке",
"err.icon.not_in_folder":"Иконка должна находиться в папке icons","err.icon.empty":"Выберите непустую иконку размером до 2 МиБ",
"err.exe.symlink_instead":"Нельзя использовать символическую ссылку вместо EXE",
"err.process.exited":"Процесс завершился неожиданно — подробности в журнале приложения.",
"err.queue.stopped":"Очередь остановлена — подробности в журнале приложения.",
"err.exe.symlink_blocked":"Нельзя записать EXE через символическую ссылку",
"err.exe.foreign_file":"Файл уже существует и не принадлежит worthlesstask",
"net.aborted":"Запрос прерван или превышено время ожидания",
"net.offline":"Нет связи с локальной программой. Проверьте, что worthlesstask запущен.",
"http.generic":"Ошибка запроса: ",
"theme.toDark":"Включить тёмную тему","theme.toLight":"Включить светлую тему","status.connecting":"Подключение к панели","session.pending":"Ожидание","session.processing":"Обработка","session.process":"Процесс","session.external":"Запущено вручную","session.connectedShort":"Подключено",
"session.multi":"Запущено несколько окон игр ({n}). Discord показывает последнее. Нажмите «Остановить», чтобы закрыть все.",
"session.externalNote":"Игра запущена вручную — через файл рядом с программой. Остановить её можно здесь.",
"session.lastAck":"Последнее подтверждение: ",
"session.ackWait":"Процесс активен. Ожидается ответ RPC от Discord.",
"session.noteIdle":"Состояние процесса и подтверждение RPC отображаются отдельно.",
"queue.dragHint":"Перетащите, чтобы изменить порядок","queue.up":"Выше","queue.down":"Ниже","queue.remove":"Убрать из очереди",
"search.emptyNone":"Ничего не найдено. Попробуйте полное или оригинальное название.",
"search.noFile":"В каталоге нет прямого EXE — обход Carrier + IPC настроится автоматически",
"search.error":"Ошибка поиска","search.changedHint":"Нажмите «Найти» для нового запроса","search.changed":"Запрос изменён",
"search.initial":"Введите название для поиска","search.idle":"Игры из каталога появятся здесь",
"notify.added":"Игра добавлена, обход и EXE подготовлены","notify.addedRun":"Игра добавлена, запуск начат","notify.exeSaved":"Имя EXE сохранено",
"notify.startRequested":"Запрос на запуск принят",
"notify.prepareDone":"EXE создан в папке workers — нажмите «Запустить» или откройте его двойным щелчком.",
"notify.iconTooLarge":"Иконка должна быть не больше 2 МиБ","notify.iconSaved":"Иконка сохранена. Она применится к окну при следующем запуске.",
"notify.stopRequested":"Запрос на остановку принят","notify.sessionDeleted":"Сессия удалена","notify.queueCleared":"Очередь очищена","notify.queueStarted":"Очередь запущена",
"card.fileTip":"Файл: {p}\nНажмите «Запустить» или откройте его двойным щелчком.","card.processTip":"Имя процесса: ","card.exeFailed":"Не удалось создать EXE: ",
"reason.no_exe":"EXE не задан. Укажите имя файла или нажмите «Синхронизировать квесты».",
"reason.manual":"Имя EXE указано вручную. Проверьте, что оно совпадает с процессом из каталога Discord, или используйте синхронизацию обхода.",
"reason.derived":"Discord не публикует прямой файл для этой игры. Нажмите «Синхронизировать квесты», чтобы автоматически привязать Carrier-обход."
}};
window.I18N=I18N;window.worthlesstaskLang=()=>ui.lang;
const ui={state:null,selected:null,candidates:[],cards:new Map(),busy:new Set(),online:false,searchSeq:0,searchController:null,refreshing:null,queueKey:'',questKey:'',exeEditing:null,view:'home',lang:'en',searchBusy:false,minutesSynced:false};
function text(el,value){if(!el)return;const s=String(value??'');if(el.textContent!==s)el.textContent=s}
function setText(el,value){const label=el&&el.querySelector('.bl');text(label||el,value)}
function node(tag,cls,value){const e=document.createElement(tag);if(cls)e.className=cls;if(value!==undefined)e.textContent=value;return e}
function icon(sym,cls){const s=document.createElementNS(SVGNS,'svg');s.setAttribute('class',cls||'i');s.setAttribute('viewBox','0 0 24 24');s.setAttribute('aria-hidden','true');const u=document.createElementNS(SVGNS,'use');u.setAttribute('href','#ic-'+sym);s.append(u);return s}
function notify(message,error=false){text($('toast'),message);$('toast').hidden=false;$('toast').classList.toggle('error',error);clearTimeout(notify.timer);notify.timer=setTimeout(()=>$('toast').hidden=true,4800)}
async function api(path,options={}){const {timeout=12000,signal,...rest}=options;const controller=new AbortController();const abort=()=>controller.abort();if(signal)signal.addEventListener('abort',abort,{once:true});const timer=setTimeout(abort,timeout);try{const response=await fetch(path,{...rest,signal:controller.signal});const data=await response.json();if(!response.ok){const err=new Error(serverError(data));err.code=data&&data.code||'';err.status=response.status;throw err}return data}catch(e){if(e.name==='AbortError')throw new Error(t('net.aborted'));if(e instanceof TypeError)throw new Error(t('net.offline'));throw e}finally{clearTimeout(timer);if(signal)signal.removeEventListener('abort',abort)}}
const post=(path,payload)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload||{})});

function t(key){const pack=I18N[ui.lang]||I18N.en;return pack[key]!==undefined?pack[key]:(I18N.en[key]!==undefined?I18N.en[key]:'')}
function serverError(data){const code=data&&data.code;if(code){const v=t('err.'+code);if(v)return v}return (data&&data.error)||t('http.generic')}
function moveIndicator(){const tabs=$('navTabs'),ind=$('tabIndicator');if(!tabs||!ind)return;const active=tabs.querySelector('.tab[aria-selected="true"]');if(!active)return;ind.style.width=active.offsetWidth+'px';ind.style.transform='translateX('+active.offsetLeft+'px)'}
function applyI18n(){
document.documentElement.lang=ui.lang==='ru'?'ru':'en';
for(const el of document.querySelectorAll('[data-i18n]')){const v=t(el.dataset.i18n);if(v)text(el,v)}
for(const el of document.querySelectorAll('[data-i18n-ph]')){const v=t(el.dataset.i18nPh);if(v)el.setAttribute('placeholder',v)}
for(const el of document.querySelectorAll('[data-i18n-aria]')){const v=t(el.dataset.i18nAria);if(v)el.setAttribute('aria-label',v)}
for(const b of document.querySelectorAll('[data-lang]'))b.setAttribute('aria-pressed',String(b.dataset.lang===ui.lang));
setText($('search'),ui.searchBusy?t('search.busy'):t('search.submit'));
setText($('syncQuests'),ui.busy.has('sync')?t('quests.syncing'):t('quests.sync'));
text($('connectionText'),ui.online?t('status.connected'):(ui.state?t('status.offline'):t('status.connecting')));
syncThemeLabel();
moveIndicator();requestAnimationFrame(moveIndicator)}
function themeIsDark(){return document.documentElement.getAttribute('data-theme')==='dark'}
function syncThemeLabel(){const btn=$('themeToggle');if(!btn)return;const label=t(themeIsDark()?'theme.toLight':'theme.toDark');btn.setAttribute('aria-pressed',String(themeIsDark()));btn.setAttribute('aria-label',label);btn.title=label}
function applyTheme(dark,persist){document.documentElement.setAttribute('data-theme',dark?'dark':'light');if(persist)try{localStorage.setItem('worthlesstask.theme',dark?'dark':'light')}catch(_){}syncThemeLabel()}
$('themeToggle').addEventListener('click',()=>applyTheme(!themeIsDark(),true));
function setLang(lang){if(lang!=='en'&&lang!=='ru')return;ui.lang=lang;try{localStorage.setItem('worthlesstask.lang',lang)}catch(_){}ui.questKey='';applyI18n();if(ui.state)render(ui.state)}
try{const saved=localStorage.getItem('worthlesstask.lang');if(saved==='en'||saved==='ru')ui.lang=saved}catch(_){}
document.querySelectorAll('[data-lang]').forEach(b=>b.addEventListener('click',()=>setLang(b.dataset.lang)));
window.addEventListener('resize',moveIndicator);
function playEnter(view){const inner=view.querySelector('.view-inner');if(!inner)return;inner.classList.remove('is-entering');void inner.offsetWidth;inner.classList.add('is-entering')}

const scrollMemory={home:0,play:0};
function showView(name,focusId){const next=name==='play'?'play':'home';if(next===ui.view){if(focusId){const el=$(focusId);if(el)el.focus()}return}
scrollMemory[ui.view]=window.scrollY;
ui.view=next;
const home=$('view-home'),play=$('view-play');
home.hidden=next!=='home';play.hidden=next!=='play';
$('tabHome').setAttribute('aria-selected',String(next==='home'));$('tabPlay').setAttribute('aria-selected',String(next==='play'));
$('tabHome').tabIndex=next==='home'?0:-1;$('tabPlay').tabIndex=next==='play'?0:-1;
window.scrollTo(0,scrollMemory[next]);
if(location.hash.slice(1)!==next)history.replaceState(null,'','#'+next);
moveIndicator();playEnter(next==='home'?home:play);
if(focusId){const el=$(focusId);if(el)el.focus()}}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.view)));
document.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.goto,b.dataset.focus)));
window.addEventListener('hashchange',()=>showView(location.hash.slice(1)));
$('navTabs').addEventListener('keydown',e=>{const tabs=[...$('navTabs').querySelectorAll('.tab')];const i=tabs.indexOf(document.activeElement);if(i<0)return;let n=null;
if(e.key==='ArrowRight'||e.key==='ArrowDown')n=(i+1)%tabs.length;else if(e.key==='ArrowLeft'||e.key==='ArrowUp')n=(i-1+tabs.length)%tabs.length;
else if(e.key==='Home')n=0;else if(e.key==='End')n=tabs.length-1;
else if(e.key===' '||e.key==='Enter'){e.preventDefault();tabs[i].click();return}
if(n===null)return;e.preventDefault();tabs[n].focus();tabs[n].click()});

function imageBox(){const box=node('div','icon-box');box.append(icon('image','i ph'));const img=node('img');img.alt='';img.loading='lazy';img.decoding='async';img.hidden=true;img.addEventListener('error',()=>{img.hidden=true});box.append(img);return{box,img,url:null}}
function setImage(ref,url,version){if(url){try{const u=new URL(url,location.origin);if(u.origin!==location.origin&&u.hostname!=='cdn.discordapp.com')url=null;else if(u.origin===location.origin&&version)u.searchParams.set('v',version);if(url)url=u.href}catch{url=null}}if(ref.url===url)return;ref.url=url;ref.img.hidden=!url;if(url)ref.img.src=url;else ref.img.removeAttribute('src')}
function button(label,kind,slug,cls='btn small ghost',sym){const b=node('button',cls);b.type='button';b.dataset.act=kind;if(slug)b.dataset.slug=slug;if(sym)b.append(icon(sym,'i xs'));b.append(node('span','bl',label));return b}
function iconButton(sym,kind,slug,cls,label){const b=node('button',cls);b.type='button';b.dataset.act=kind;if(slug)b.dataset.slug=slug;b.append(icon(sym,cls==='q-del'?'i xxs':'i xs'));if(label)b.setAttribute('aria-label',label);return b}
function findQuestForGame(g,quests){if(!Array.isArray(quests))return null;return quests.find(q=>q.primary_app_id===g.application_id||(Array.isArray(q.accepted_app_ids)&&q.accepted_app_ids.includes(g.application_id)))||null}
function makeCard(g){const root=node('article','game');root.dataset.slug=g.slug;const im=imageBox(),info=node('div','game-info'),titleRow=node('div','game-title-row'),name=node('div','game-name'),meta=node('div','game-meta'),tags=node('div','game-tags'),badge=node('span','badge'),bypassBadge=node('span','badge sub'),questBadge=node('span','badge quest');titleRow.append(name);tags.append(bypassBadge,questBadge);info.append(titleRow,meta,tags);const reason=node('p','reason');const actions=node('div','game-actions');const icon_=button(t('library.icon'),'icon',g.slug,'btn small ghost','image'),queue=button(t('library.queueAdd'),'queue',g.slug,'btn small ghost','queue'),del=button(t('library.delete'),'delete',g.slug,'btn small ghost','trash'),rename=button(t('library.exeName'),'rename',g.slug,'btn small ghost','edit'),prepare=button(t('library.makeExe'),'prepare',g.slug,'btn small ghost','chip'),start=button(t('library.start'),'start',g.slug,'btn small primary start','play');const file=node('input','icon-picker');file.type='file';file.accept='.ico,.png,.jpg,.jpeg,.bmp,.webp';file.dataset.icon=g.slug;const exeRow=node('div','exe-row');exeRow.hidden=true;const exeInput=node('input');exeInput.type='text';exeInput.maxLength=180;exeInput.placeholder=t('library.exePlaceholder');exeInput.setAttribute('aria-label',t('library.exeAria'));const exeSave=button(t('library.save'),'exe-save',g.slug,'btn small primary','check');exeRow.append(exeInput,exeSave);actions.append(icon_,queue,del,rename,prepare,start,file);root.append(im.box,info,badge,actions,reason,exeRow);return{root,im,name,meta,tags,badge,bypassBadge,questBadge,reason,icon:icon_,queue,del,rename,prepare,start,file,exeRow,exeInput,exeSave}}
function updateCard(ref,g,s){const active=s.active?.slug===g.slug;const pending=s.operation?.slug===g.slug;const locked=!!s.operation||ui.busy.size>0||!ui.online;const ready=!!g.worker_ready;const derived=g.can_start&&g.executable_source!=='catalogue'&&!g.bypass_mode;const exeDisplay=g.executable_rel||g.executable||t('meta.noExe');text(ref.name,g.game_name);text(ref.meta,'ID '+g.application_id+' · '+exeDisplay+(g.epic_app_id?' · Epic SKU':''));ref.meta.title=g.worker_path?t('card.fileTip').replace('{p}',g.worker_path):(exeDisplay?t('card.processTip')+exeDisplay:'');text(ref.badge,active?t('badge.session'):!g.can_start?t('badge.noExe'):derived?t('badge.outside'):ready?t('badge.ready'):t('badge.missing'));ref.badge.className='badge '+(active?'run':g.can_start&&ready&&!derived?'':'warn');
const bmode=g.bypass_mode||(g.executable_rel&&g.executable_rel.includes('/')?'subdir_exe':(g.executable_source==='catalogue'?'native_exe':''));const btext=bmode?t('bypass.'+bmode):'';text(ref.bypassBadge,btext);ref.bypassBadge.hidden=!btext;
const mq=findQuestForGame(g,s.quests);const qpct=mq?(mq.is_completed?'100%':mq.progress_percent+'%'):'';const qtext=mq?(mq.orb_reward?mq.orb_reward+' '+t('quests.orbs')+' · '+(mq.is_completed?t('quests.completed'):qpct):mq.quest_name):'';text(ref.questBadge,qtext);ref.questBadge.hidden=!qtext;ref.tags.hidden=ref.bypassBadge.hidden&&ref.questBadge.hidden;
ref.root.classList.toggle('active',active);const reasonKey=g.availability_reason&&t(g.availability_reason)?g.availability_reason:null;const wcode=g.worker_error_code&&t('err.'+g.worker_error_code);const note=reasonKey?t(reasonKey):(g.worker_error?(wcode||t('card.exeFailed')+g.worker_error):'');text(ref.reason,note||'');ref.reason.hidden=!note;setImage(ref.im,g.icon_url,g.icon_version);setText(ref.start,pending?t('library.starting'):active?t('library.running'):t('library.start'));ref.start.disabled=locked||active||!g.can_start;ref.start.classList.toggle('is-running',active||pending);ref.prepare.hidden=!g.can_start||ready;ref.prepare.disabled=locked;ref.rename.disabled=locked;ref.exeSave.disabled=locked;ref.exeRow.hidden=ui.exeEditing!==g.slug;ref.icon.disabled=ui.busy.size>0;ref.del.disabled=locked||active;setText(ref.queue,s.queue.includes(g.slug)?t('library.queueRemove'):t('library.queueAdd'));ref.queue.disabled=locked||!g.can_start;setText(ref.icon,t('library.icon'));setText(ref.del,t('library.delete'));setText(ref.rename,t('library.exeName'));setText(ref.prepare,t('library.makeExe'));setText(ref.exeSave,t('library.save'));if(document.activeElement!==ref.exeInput){ref.exeInput.placeholder=t('library.exePlaceholder');ref.exeInput.setAttribute('aria-label',t('library.exeAria'))}}

function renderQuests(s){const quests=Array.isArray(s.quests)?s.quests:[];text($('questCount'),String(quests.length));$('questEmpty').hidden=quests.length>0;const qk=JSON.stringify([ui.lang,quests.map(q=>[q.quest_id,q.progress_percent,q.is_enrolled,q.is_completed,q.orb_reward])]);if(ui.questKey===qk)return;ui.questKey=qk;$('questList').replaceChildren();for(const q of quests){const isDone=!!q.is_completed;const pct=isDone?100:(q.progress_percent||0);const card=node('div','quest-card'+(isDone?' completed':(q.is_enrolled?' enrolled':'')));const main=node('div','quest-main');const title=node('div','quest-title',q.game_title||q.quest_name);const statusText=isDone?t('quests.completed'):(q.is_enrolled?t('quests.enrolled'):t('quests.available'));const sub=node('div','quest-sub',statusText+' · '+q.target_minutes+' '+t('queue.unitShort')+(q.orb_reward?' · '+q.orb_reward+' '+t('quests.orbs'):''));const bar=node('div','quest-bar');const fill=node('span');fill.style.width=pct+'%';bar.append(fill);main.append(title,sub,bar);const pill=node('span','badge '+(isDone?'':(q.is_enrolled?'run':'warn')),pct+'%');card.append(main,pill);$('questList').append(card)}}

function render(s){ui.state=s;const op=s.operation,a=s.active,locked=!!op||ui.busy.size>0||!ui.online;
if(!ui.minutesSynced&&s.games?.length&&document.activeElement!==$('queueMinutes')){const qg=s.queue?.length?s.games.find(g=>g.slug===s.queue[0]):s.games[0];if(qg?.duration_minutes)$('queueMinutes').value=String(qg.duration_minutes);ui.minutesSynced=true}
const seen=new Set();for(const g of s.games){seen.add(g.slug);let ref=ui.cards.get(g.slug);if(!ref){ref=makeCard(g);ref.root.style.animationDelay=(ui.cards.size*.035)+'s';ui.cards.set(g.slug,ref);$('games').append(ref.root)}updateCard(ref,g,s)}for(const[slug,ref]of ui.cards){if(!seen.has(slug)){ref.root.remove();ui.cards.delete(slug)}}$('libraryEmpty').hidden=!!s.games.length;text($('gameCount'),s.games.length+' '+t('library.unit'));
$('syncQuests').disabled=locked;setText($('syncQuests'),ui.busy.has('sync')?t('quests.syncing'):t('quests.sync'));
renderQuests(s);
text($('activeName'),a?.game_name||(op?.slug?s.games.find(g=>g.slug===op.slug)?.game_name:t('active.idle')));const rpc=a?.rpc_state;const labels={connected:t('rpc.connected'),connecting:t('rpc.connecting'),reconnecting:t('rpc.reconnecting'),error:t('rpc.error')};text($('activeState'),op?(op.kind==='start'?t('active.prepare'):t('active.stopping')):(a?labels[rpc]||t('active.unconfirmed'):t('active.ready')));text($('sessionBadge'),op?t('session.processing'):rpc==='connected'?(a?.reason==='external'?t('session.external'):t('session.connectedShort')):a?t('session.process'):t('session.pending'));$('sessionBadge').className='badge '+(op||rpc==='connected'?'run':a?'':'warn');const seconds=Math.floor(a?.uptime_s||0);text($('elapsed'),String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0'));text($('pid'),a?.pid||'—');text($('sessionNote'),a?.rpc_error||(a?.also_running>0?t('session.multi').replace('{n}',a.also_running+1):a?.reason==='external'?t('session.externalNote'):a?.last_ack?t('session.lastAck')+new Date(a.last_ack).toLocaleTimeString(ui.lang==='ru'?'ru-RU':'en-US'):a?t('session.ackWait'):t('session.noteIdle')));$('stopAll').disabled=locked||!a;$('resetSession').disabled=locked||(!a&&!s.last_error);
const error=(s.last_error_code&&t('err.'+s.last_error_code))||s.last_error||'';const ge=$('globalError');if(ge){text(ge,error);ge.hidden=!error}
const key=JSON.stringify([s.queue,s.games.map(g=>[g.slug,g.game_name,g.duration_minutes])]);if(ui.queueKey!==key){ui.queueKey=key;renderQueue(s)}const rows=[...$('queue').querySelectorAll('.queue-item')];rows.forEach((li,i)=>{for(const b of li.querySelectorAll('button')){const act=b.dataset.act;b.disabled=locked||(act==='queue-up'&&i===0)||(act==='queue-down'&&i===rows.length-1)}});const bar=$('queue').querySelector('.queue-item.current .q-bar');if(bar){const mins=ui.state?.games.find(g=>g.slug===ui.state.active?.slug)?.duration_minutes||15;const left=s.next_switch_in_s;bar.style.width=(left!=null&&mins>0)?Math.max(0,Math.min(100,(1-left/(mins*60))*100))+'%':'0'}$('queueEmpty').hidden=!!s.queue.length;text($('queueCount'),s.queue.length+' '+t('queue.of')+' '+s.games.length);$('startQueue').disabled=locked||!s.queue.length||s.queue_running;setText($('startQueue'),s.queue_running?t('queue.restart'):t('queue.start'));$('clearQueue').disabled=locked||!s.queue.length;text($('queueStatus'),s.queue_running?t('queue.running')+(s.next_switch_in_s!=null?' · '+Math.ceil(s.next_switch_in_s)+' '+t('queue.unitShort'):''):t('queue.stopped'));selectionState()}
function renderQueue(s){$('queue').replaceChildren();s.queue.forEach((slug,i)=>{const g=s.games.find(x=>x.slug===slug);const current=s.active?.slug===slug;const li=node('li','queue-item'+(current?' current':''));li.draggable=true;li.dataset.slug=slug;li.style.animationDelay=(i*.04)+'s';li.title=t('queue.dragHint');li.append(node('span','q-grip',''),node('span','q-num',String(i+1)),node('span','q-name',g?.game_name||slug),node('span','q-min',(g?.duration_minutes||15)+t('queue.unitShort')));
const order=node('div','q-order');const up=iconButton('up','queue-up',slug,'q-move',t('queue.up'));up.disabled=i===0;const down=iconButton('down','queue-down',slug,'q-move',t('queue.down'));down.disabled=i===s.queue.length-1;order.append(up,down);const rm=iconButton('close','queue',slug,'q-del',t('queue.remove'));li.append(order,rm);if(current)li.append(node('span','q-bar'));$('queue').append(li)})}
let dragSlug=null;
function clearDropMarks(){for(const el of $('queue').children)el.classList.remove('dragging','drop-before','drop-after')}
$('queue').addEventListener('dragstart',e=>{const li=e.target.closest('.queue-item');if(!li||ui.busy.size)return;dragSlug=li.dataset.slug;li.classList.add('dragging');e.dataTransfer.effectAllowed='move';try{e.dataTransfer.setData('text/plain',dragSlug)}catch(_){}});
$('queue').addEventListener('dragover',e=>{if(!dragSlug)return;e.preventDefault();e.dataTransfer.dropEffect='move';const li=e.target.closest('.queue-item');for(const el of $('queue').children)el.classList.remove('drop-before','drop-after');if(!li||li.dataset.slug===dragSlug)return;const box=li.getBoundingClientRect();li.classList.add(e.clientY<box.top+box.height/2?'drop-before':'drop-after')});
$('queue').addEventListener('drop',e=>{if(!dragSlug)return;e.preventDefault();const li=e.target.closest('.queue-item');const slug=dragSlug;const target=li?li.dataset.slug:null;const before=li?li.classList.contains('drop-before'):false;dragSlug=null;clearDropMarks();if(!target||target===slug)return;
const q=[...(ui.state?.queue||[])];const from=q.indexOf(slug);if(from<0)return;q.splice(from,1);let to=q.indexOf(target);if(to<0)return;if(!before)to+=1;q.splice(to,0,slug);mutation('queue',()=>post('/api/queue',{slugs:q,minutes:minutes()}))});
$('queue').addEventListener('dragend',()=>{dragSlug=null;clearDropMarks()});
function selectionState(){const selected=ui.selected;const existing=ui.state?.games.find(g=>g.application_id===selected?.id);const exists=!!existing;const busy=ui.busy.has('add');text($('selectionLabel'),selected?selected.name+' · ID '+selected.id:t('selection.none'));$('addSelected').disabled=!selected||exists||busy||!ui.online;$('addAndRun').disabled=!selected||busy||!ui.online||(exists&&(!existing.can_start||ui.state?.active?.slug===existing.slug));setText($('addSelected'),busy?t('add.busy'):exists?t('add.exists'):t('add'));setText($('addAndRun'),busy?'…':exists?t('library.start'):t('addRun'))}
async function refresh(){if(ui.refreshing)return ui.refreshing;ui.refreshing=(async()=>{try{const s=await api('/api/state');ui.online=true;text($('connectionText'),t('status.connected'));$('connectionDot').classList.remove('off');render(s)}catch(e){ui.online=false;text($('connectionText'),t('status.offline'));$('connectionDot').classList.add('off');if(ui.state)render(ui.state)}finally{ui.refreshing=null}})();return ui.refreshing}
async function poll(){try{await refresh()}catch(e){/* a failed tick must never stop the loop */}setTimeout(poll,document.hidden?6000:1500)}
async function mutation(key,action,success){if(ui.busy.size)return;ui.busy.add(key);if(ui.state)render(ui.state);try{const res=await action();const msg=typeof success==='function'?success(res):success;if(msg)notify(msg);await refresh()}catch(e){notify(e.message,true)}finally{ui.busy.delete(key);if(ui.state)render(ui.state)}}
function renderResults(results){$('results').replaceChildren();ui.selected=null;ui.candidates=results;$('searchEmpty').hidden=results.length>0;text($('searchEmpty'),t('search.emptyNone'));for(const [i,r] of results.entries()){const card=node('button','result');card.type='button';card.dataset.resultId=r.id;card.setAttribute('aria-pressed','false');card.style.animationDelay=(i*.03)+'s';const im=imageBox();setImage(im,r.icon_url,'');const content=node('div','result-body');content.append(node('div','name',r.name),node('div','meta','ID '+r.id),node('div','meta',r.executables?.length?r.executables.join(' · '):t('search.noFile')));const check=node('span','check');check.append(icon('check','i'));card.append(im.box,content,check);card.addEventListener('click',()=>{ui.selected=r;for(const b of $('results').children)b.setAttribute('aria-pressed',String(b===card));selectionState()});$('results').append(card)}selectionState()}
$('searchForm').addEventListener('submit',async e=>{e.preventDefault();const q=$('query').value.trim();if(!q)return;const seq=++ui.searchSeq;ui.searchController?.abort();ui.searchController=new AbortController();ui.selected=null;selectionState();$('search').disabled=true;ui.searchBusy=true;setText($('search'),t('search.busy'));text($('searchStatus'),t('search.loading'));$('results').setAttribute('aria-busy','true');$('results').replaceChildren(node('div','pulse'),node('div','pulse'));$('searchEmpty').hidden=true;try{const data=await api('/api/search?q='+encodeURIComponent(q),{signal:ui.searchController.signal,timeout:95000});if(seq!==ui.searchSeq)return;renderResults(data.results);text($('searchStatus'),data.results.length?t('search.found').replace('{n}',data.results.length):t('search.none'))}catch(e){if(seq!==ui.searchSeq)return;renderResults([]);text($('searchStatus'),t('search.error'));text($('searchEmpty'),e.message)}finally{if(seq===ui.searchSeq){$('results').setAttribute('aria-busy','false');$('search').disabled=false;ui.searchBusy=false;setText($('search'),t('search.submit'))}}});
$('query').addEventListener('input',()=>{if(ui.searchController){ui.searchSeq++;ui.searchController.abort();ui.searchController=null;$('search').disabled=false;ui.searchBusy=false;setText($('search'),t('search.submit'));$('results').replaceChildren();$('searchEmpty').hidden=false;text($('searchEmpty'),t('search.changedHint'));text($('searchStatus'),t('search.changed'));ui.selected=null;selectionState()}});
$('addSelected').addEventListener('click',()=>{const r=ui.selected;if(!r)return;mutation('add',()=>post('/api/games',{game_name:r.name,application_id:r.id}),t('notify.added'))});
$('addAndRun').addEventListener('click',()=>{const r=ui.selected;if(!r)return;const existing=ui.state?.games.find(g=>g.application_id===r.id);if(existing){mutation('start',()=>post('/api/play',{slug:existing.slug}),t('notify.startRequested'));return}mutation('add',()=>post('/api/games',{game_name:r.name,application_id:r.id,autostart:true}),t('notify.addedRun'))});
$('syncQuests').addEventListener('click',()=>mutation('sync',()=>post('/api/quests/sync',{auto_add:true}),res=>{const n=(res?.sync?.added_quests?.length||0)+(res?.sync?.updated_slugs?.length||0);return t('quests.synced').replace('{n}',n)}));
function minutes(){const n=Number($('queueMinutes').value);if(!Number.isInteger(n)||n<1||n>1440)throw new Error(t('err.queue.minutes'));return n}
$('queueMinutes').addEventListener('change',()=>{if(!ui.state?.queue?.length||ui.busy.size)return;try{const m=minutes();mutation('queue',()=>post('/api/queue',{slugs:ui.state.queue,minutes:m}))}catch(e){notify(e.message,true)}});
function reorder(slug,delta){const q=[...(ui.state?.queue||[])];const i=q.indexOf(slug);const j=i+delta;if(i<0||j<0||j>=q.length)return;[q[i],q[j]]=[q[j],q[i]];mutation('queue',()=>post('/api/queue',{slugs:q,minutes:minutes()}))}
const modal={root:$('modalRoot'),title:$('modalTitle'),msg:$('modalMsg'),input:$('modalInput'),
  ok:$('modalOk'),cancel:$('modalCancel'),opener:null,resolve:null};
function dialogOpen(opts,withInput){
  return new Promise(resolve=>{
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
document.addEventListener('click',async e=>{const b=e.target.closest('[data-act]');if(!b||b.disabled)return;const slug=b.dataset.slug,kind=b.dataset.act;if(kind==='icon'){ui.cards.get(slug)?.file.click();return}if(kind==='queue-up'){reorder(slug,-1);return}if(kind==='queue-down'){reorder(slug,1);return}if(kind==='rename'){const ref=ui.cards.get(slug);ui.exeEditing=ui.exeEditing===slug?null:slug;if(ref&&ui.exeEditing){const g=ui.state?.games.find(x=>x.slug===slug);ref.exeInput.value=(g&&g.executable)||''}if(ui.state)render(ui.state);if(ref&&ui.exeEditing)ref.exeInput.focus();return}if(kind==='exe-save'){const ref=ui.cards.get(slug);const name=(ref?ref.exeInput.value:'').trim();ui.exeEditing=null;mutation('exe',()=>post('/api/executable/'+encodeURIComponent(slug),{executable:name}),t('notify.exeSaved'));return}if(kind==='delete'&&!await showConfirm({title:t('dlg.delTitle'),message:t('dlg.delMsg'),confirmText:t('dlg.delete'),cancelText:t('dlg.cancel'),danger:true}))return;mutation(kind,async()=>{if(kind==='start')await post('/api/play',{slug});else if(kind==='stop')await post('/api/stop');else if(kind==='prepare')await post('/api/prepare/'+encodeURIComponent(slug));else if(kind==='delete')await api('/api/games/'+encodeURIComponent(slug),{method:'DELETE'});else if(kind==='queue'){const s=await api('/api/state');await post('/api/queue',{slugs:s.queue.includes(slug)?s.queue.filter(x=>x!==slug):[...s.queue,slug],minutes:minutes()})}},kind==='start'?t('notify.startRequested'):kind==='prepare'?t('notify.prepareDone'):kind==='delete'?t('dlg.deleted'):null)});
document.addEventListener('keydown',e=>{if(!ui.exeEditing)return;const input=e.target.closest?.('.exe-row input');if(!input)return;if(e.key==='Enter'){e.preventDefault();input.closest('.exe-row').querySelector('[data-act="exe-save"]').click()}else if(e.key==='Escape'){ui.exeEditing=null;if(ui.state)render(ui.state)}});
document.addEventListener('change',e=>{const slug=e.target.dataset?.icon,file=e.target.files?.[0];if(!slug||!file)return;if(file.size>2097152){notify(t('notify.iconTooLarge'),true);e.target.value='';return}mutation('icon',()=>api('/api/icon/'+encodeURIComponent(slug),{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name),'Content-Type':'application/octet-stream'},body:file}),t('notify.iconSaved')).finally(()=>e.target.value='')});
$('stopAll').onclick=()=>mutation('stop',()=>post('/api/stop'),t('notify.stopRequested'));
$('resetSession').onclick=async()=>{if(!await showConfirm({title:t('dlg.resetTitle'),message:t('dlg.resetMsg'),confirmText:t('dlg.end'),cancelText:t('dlg.cancel'),danger:true}))return;mutation('reset',()=>post('/api/session/reset'),t('notify.sessionDeleted'))};
$('clearQueue').onclick=()=>mutation('queue',()=>post('/api/queue',{slugs:[]}),t('notify.queueCleared'));
$('startQueue').onclick=()=>mutation('queue',async()=>{await post('/api/queue',{slugs:ui.state.queue,minutes:minutes()});await post('/api/queue/start')},t('notify.queueStarted'));
applyI18n();
showView(location.hash.slice(1));
poll();
</script></body></html>'''
