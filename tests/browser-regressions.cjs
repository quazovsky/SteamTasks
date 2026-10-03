/* Browser-only contract tests. Responses are controlled here, never in production. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { expect } = require('@playwright/test');

const base = process.env.WORTHLESSTASK_TEST_URL || 'http://127.0.0.1:8795';
const output = path.resolve(__dirname, '../build/qa-interface');
const executablePath = process.env.WORTHLESSTASK_TEST_BROWSER;
const tests = [];
const state = {
  games: [
    {slug:'arknights-endfield',game_name:'ARKNIGHTS: ENDFIELD',application_id:'1461154307171811401',executable:'endfield.exe',can_start:true,duration_minutes:15,icon_url:null},
    {slug:'resident-evil-requiem',game_name:'Resident Evil Requiem',application_id:'1456485028350656512',executable:null,can_start:false,duration_minutes:15,icon_url:null,availability_reason:'В каталоге нет EXE. Автоматический запуск недоступен.'}
  ], active:null, operation:null, queue:[], queue_running:false, next_switch_in_s:null, last_error:null
};
const candidates = [
  {id:'1384276457596911676',name:'PEAK',executables:['peak.exe'],icon_url:null},
  {id:'1461154307171811401',name:'ARKNIGHTS: ENDFIELD',executables:['endfield.exe'],icon_url:null}
];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const browser = await chromium.launch({headless:true, executablePath, args:['--disable-gpu']});
  const context = await browser.newContext({viewport:{width:1380,height:1040},colorScheme:'dark'});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let stateReads = 0, launches = 0, added = null, uploadCount = 0, resets = 0;
  let failStart = false;
  async function reply(route, data, status=200) {
    await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  }
  await page.route('**/api/state', async route => {stateReads++; await reply(route,state)});
  await page.route('**/api/search?*', async route => {
    const q = new URL(route.request().url()).searchParams.get('q');
    await delay(q === 'slow' ? 1000 : 180);
    if(q === 'error') return reply(route,{error:'Каталог временно недоступен'},503);
    await reply(route,{results:q === 'none' ? [] : candidates});
  });
  await page.route('**/api/games', async route => {
    added = route.request().postDataJSON();
    assert.equal(added.application_id, candidates[0].id);
    state.games.push({slug:'peak',game_name:added.game_name,application_id:added.application_id,executable:'peak.exe',can_start:true,duration_minutes:15,icon_url:null});
    await reply(route,state.games.at(-1));
  });
  await page.route('**/api/play', async route => {
    launches++;
    // A known failure carries a code, which is what makes it translatable.
    if(failStart) return reply(route,{error:'EXE не найден: test-missing.exe',code:'exe.missing'},400);
    const {slug} = route.request().postDataJSON();
    assert.equal(slug,'arknights-endfield');
    state.operation={kind:'start',slug,status:'pending'};
    await delay(350);
    await reply(route,state,202);
    await delay(450);
    state.operation=null;
    state.active={slug,game_name:'ARKNIGHTS: ENDFIELD',pid:1000,uptime_s:5,reason:'manual',rpc_state:'connecting',last_ack:null};
  });
  await page.route('**/api/stop', async route => {
    state.active=null; state.operation=null;
    await reply(route,state,202);
  });
  await page.route('**/api/session/reset', async route => {
    resets++;
    state.active=null; state.operation=null; state.last_error=null;
    await reply(route,state);
  });
  await page.route('**/api/queue', async route => {
    state.queue=route.request().postDataJSON().slugs;
    await reply(route,{queue:state.queue});
  });
  await page.route('**/api/icon/*', async route => {
    if(route.request().method() !== 'POST') return route.fulfill({status:404,body:''});
    uploadCount++;
    assert.ok(route.request().headers()['x-filename'].includes('test.ico'));
    await reply(route,{ok:true});
  });

  try {
    await page.goto(base);
    // The page owns its own wording. Read the active locale from it so these
    // assertions hold in every language instead of pinning one.
    const i18n = await page.evaluate(() => ({
      table: window.I18N || {},
      lang: window.worthlesstaskLang ? window.worthlesstaskLang() : 'en',
    }));
    const T = key => i18n.table[i18n.lang][key];
    await expect(page.locator('#connectionText')).toHaveText(T('status.connected'));

    // Home is the landing view: it explains the tool and links into the game space.
    await expect(page.locator('#view-home')).toBeVisible();
    await expect(page.locator('#view-play')).toBeHidden();
    await expect(page.locator('#tabHome')).toHaveAttribute('aria-selected','true');
    await expect(page.locator('.feature')).toHaveCount(0);
    await expect(page.locator('.moon-scene')).toHaveCount(1);
    await expect(page.locator('.hero-word')).toHaveText('worthlesstask');
    await expect(page.locator('.chip .env')).toHaveCount(0);
    tests.push('home tab, moon scene and monochrome status rail');

    await page.locator('[data-goto="play"]').first().click();
    await expect(page.locator('#view-play')).toBeVisible();
    await expect(page.locator('#view-home')).toBeHidden();
    await expect(page.locator('#tabPlay')).toHaveAttribute('aria-selected','true');
    await expect(page.locator('#games article.game')).toHaveCount(2);
    await expect(page.locator('article.game[data-slug="resident-evil-requiem"] .start')).toBeDisabled();
    tests.push('navigation into the game space and missing-exe action disabled');

    await page.locator('#tabHome').click();
    await expect(page.locator('#view-home')).toBeVisible();
    await page.locator('#tabPlay').click();
    await expect(page.locator('#view-play')).toBeVisible();
    tests.push('tabs switch both ways');

    const card = page.locator('#games article.game[data-slug="arknights-endfield"]');
    await card.evaluate(el => window.originalCard = el);
    // Layout geometry, not viewport geometry: focusing a field lower down may scroll.
    const geometry = () => card.evaluate(el => ({
      top: el.offsetTop, left: el.offsetLeft, width: el.offsetWidth, height: el.offsetHeight,
      same: el === window.originalCard,
    }));
    const before = await geometry();
    await page.locator('#queueMinutes').fill('23');
    await page.locator('#queueMinutes').focus();
    const previousReads = stateReads;
    await expect.poll(() => stateReads, {timeout:7000}).toBeGreaterThan(previousReads+1);
    assert.deepEqual(await geometry(), before);
    await expect(page.locator('#queueMinutes')).toBeFocused();
    await expect(page.locator('#queueMinutes')).toHaveValue('23');
    tests.push('polling preserves DOM identity, geometry, focus and input value');

    await page.locator('#query').fill('peak');
    await page.locator('#search').click();
    await expect(page.locator('#searchStatus')).toHaveText(T('search.loading'));
    await expect(page.locator('#results .result')).toHaveCount(2);
    await page.locator('#results .result').first().click();
    await expect(page.locator('#results .result').first()).toHaveAttribute('aria-pressed','true');
    await page.locator('#addSelected').click();
    await expect(page.locator('#games article.game')).toHaveCount(3);
    assert.deepEqual(added,{game_name:'PEAK',application_id:'1384276457596911676'});
    tests.push('search loading, selectable cards and exact selected application ID');

    await page.locator('#query').fill('slow');
    await page.locator('#search').click();
    await page.locator('#query').fill('none');
    await page.locator('#search').click();
    await expect(page.locator('#searchStatus')).toHaveText(T('search.none'));
    await expect(page.locator('#searchEmpty')).toBeVisible();
    await expect(page.locator('#results .result')).toHaveCount(0);
    await expect(page.locator('#addSelected')).toBeDisabled();
    const readsBeforeLate = stateReads;
    await expect.poll(() => stateReads, {timeout:5000}).toBeGreaterThan(readsBeforeLate);
    await expect(page.locator('#results .result')).toHaveCount(0);
    tests.push('empty results and stale response cancellation');

    await page.locator('#query').fill('error');
    await page.locator('#search').click();
    await expect(page.locator('#searchEmpty')).toContainText('Каталог временно недоступен');
    await expect(page.locator('#search')).toBeEnabled();
    tests.push('search error and retry action');

    const start = card.locator('.start');
    await start.evaluate(el => {el.click();el.click()});
    await expect.poll(()=>launches).toBe(1);
    await expect(start).toBeDisabled();
    await page.locator('#query').fill('peak');
    await page.locator('#search').click();
    await expect(page.locator('#results .result')).toHaveCount(2);
    await expect(page.locator('#activeState')).toHaveText(T('rpc.connecting'),{timeout:7000});
    assert.equal(launches,1);
    await expect(page.locator('#activeState')).not.toHaveText(T('rpc.connected'));
    state.active.rpc_state='connected';
    state.active.last_ack=new Date().toISOString();
    await expect(page.locator('#activeState')).toHaveText(T('rpc.connected'),{timeout:5000});
    state.active.rpc_state='reconnecting';
    state.active.rpc_error='Соединение потеряно';
    await expect(page.locator('#activeState')).toHaveText(T('rpc.reconnecting'),{timeout:5000});
    tests.push('double-click guarded; search works during launch; process and RPC states distinguished');

    await page.locator('#stopAll').click();
    await expect(page.locator('#activeName')).toHaveText(T('active.idle'));
    await expect(start).toBeEnabled();
    failStart=true;
    await start.click();
    // Server prose is rendered through the code, so it follows the active locale.
    await expect(page.locator('#toast')).toContainText(T('err.exe.missing'));
    await expect(start).toBeEnabled();
    tests.push('stop, missing-path feedback and retry enabled');

    // Session deletion: only reachable once there is a session or a recorded error.
    failStart=false;
    await start.click();
    await expect(page.locator('#resetSession')).toBeEnabled({timeout:7000});
    page.once('dialog', d => d.accept());
    await page.locator('#resetSession').click();
    await expect.poll(()=>resets).toBe(1);
    await expect(page.locator('#activeName')).toHaveText(T('active.idle'));
    await expect(page.locator('#resetSession')).toBeDisabled();
    tests.push('session delete is gated on a live session and clears it');

    await page.locator('#queueMinutes').fill('0');
    await card.locator('[data-act="queue"]').click();
    await expect(page.locator('#toast')).toContainText(T('err.queue.minutes'));
    await page.locator('#queueMinutes').fill('15');
    await card.locator('[data-act="queue"]').click();
    await expect(page.locator('#queue .queue-item')).toHaveCount(1);
    await card.locator('input[type="file"]').setInputFiles({name:'test.ico',mimeType:'image/x-icon',buffer:Buffer.from([0,0,1,0,1,0])});
    await expect.poll(()=>uploadCount).toBe(1);
    tests.push('queue validation and icon upload');

    // Queue is reorderable and shows the per-game duration.
    await page.locator('article.game[data-slug="peak"] [data-act="queue"]').click();
    await expect(page.locator('#queue .queue-item')).toHaveCount(2);
    await expect(page.locator('#queue .q-min').first()).toContainText(T('queue.unitShort'));
    const names = () => page.locator('#queue .q-name').allTextContents();
    const queueBefore = await names();
    await page.locator('#queue .queue-item').nth(1).locator('[data-act="queue-up"]').click();
    await expect.poll(names, {timeout:6000}).toEqual([queueBefore[1], queueBefore[0]]);
    await expect(page.locator('#queue .queue-item').first().locator('.q-num')).toHaveText('1');
    await expect(page.locator('#queue .queue-item').first().locator('[data-act="queue-up"]')).toBeDisabled();
    await page.locator('#queue .queue-item').first().locator('[data-act="queue"]').click();
    await expect(page.locator('#queue .queue-item')).toHaveCount(1);
    tests.push('queue reorder, duration labels and removal');

    // Dragging is the primary way to reorder; the arrows stay as the keyboard-accessible path.
    // Playwright's dragTo does not drive HTML5 drag-and-drop here, so the sequence the browser
    // would fire is dispatched directly — that exercises our handlers, which is the point.
    await page.locator('article.game[data-slug="peak"] [data-act="queue"]').click();
    await expect(page.locator('#queue .queue-item')).toHaveCount(2);
    await expect(page.locator('#queue .queue-item').first()).toHaveAttribute('draggable','true');
    await expect(page.locator('#queue .q-grip').first()).toBeVisible();
    const dragNames = () => page.locator('#queue .q-name').allTextContents();
    const dragBefore = await dragNames();
    await page.evaluate(() => {
      const list = document.getElementById('queue');
      const items = [...list.children];
      const dt = new DataTransfer();
      items[0].dispatchEvent(new DragEvent('dragstart', {bubbles:true, dataTransfer:dt}));
      const box = items[1].getBoundingClientRect();
      const at = {clientX:box.left+10, clientY:box.bottom-2};
      list.dispatchEvent(new DragEvent('dragover', {bubbles:true, cancelable:true, dataTransfer:dt, ...at}));
      items[1].dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:dt, ...at}));
      items[0].dispatchEvent(new DragEvent('dragend', {bubbles:true, dataTransfer:dt}));
    });
    await expect.poll(dragNames, {timeout:6000}).toEqual([dragBefore[1], dragBefore[0]]);
    tests.push('queue drag-and-drop reorders');

    // Tab switching must be imperceptible: no entrance animation, no scroll jump.
    await page.locator('#tabHome').click();
    await expect(page.locator('#view-home')).toBeVisible();
    assert.equal(await page.locator('#view-play').evaluate(el => getComputedStyle(el).animationName), 'none');
    assert.equal(await page.locator('#view-home').evaluate(el => getComputedStyle(el).animationName), 'none');
    tests.push('view switching carries no entrance animation');
    await page.locator('#tabPlay').click();
    await expect(page.locator('#view-play')).toBeVisible();

    // Language toggle: the whole interface switches, live, and survives a reload.
    await page.locator('#tabHome').click();
    const other = i18n.lang === 'en' ? 'ru' : 'en';
    await page.locator(`[data-lang="${other}"]`).click();
    await expect(page.locator('#tabHome')).toHaveText(i18n.table[other]['tab.home']);
    await expect(page.locator('.hero-word')).toHaveText('worthlesstask');
    await expect(page.locator(`[data-lang="${other}"]`)).toHaveAttribute('aria-pressed','true');
    await expect(page.locator(`[data-lang="${i18n.lang}"]`)).toHaveAttribute('aria-pressed','false');
    await expect(page.locator('html')).toHaveAttribute('lang',other);
    // Status strings come from the same table, not from a second hard-coded source.
    await expect(page.locator('#connectionText')).toHaveText(i18n.table[other]['status.connected']);
    await page.reload();
    await expect(page.locator('#tabHome')).toHaveText(i18n.table[other]['tab.home']);
    await expect(page.locator('html')).toHaveAttribute('lang',other);
    await page.locator(`[data-lang="${i18n.lang}"]`).click();
    await expect(page.locator('#tabHome')).toHaveText(T('tab.home'));
    tests.push('language toggle switches the interface and persists across reload');
    // Back to the game space: the mobile checks below assert on the search button.
    await page.locator('#tabPlay').click();
    await expect(page.locator('#view-play')).toBeVisible();

    await page.setViewportSize({width:390,height:844});
    await expect(page.locator('#search')).toBeVisible();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.emulateMedia({reducedMotion:'reduce'});
    const motion = await page.locator('#search').evaluate(el => getComputedStyle(el).transitionDuration);
    assert.ok(/^0(\.\d+)?s$/.test(motion) && parseFloat(motion) < 0.05,
      `reduced motion should collapse transitions, got ${motion}`);
    await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
    tests.push('mobile width and reduced-motion preference');

    await page.setViewportSize({width:1380,height:1040});
    await page.screenshot({path:path.join(output,'dashboard.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    const report={passed:tests.length,scenarios:tests,pageErrors:errors};
    fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } catch(error) {
    await page.screenshot({path:path.join(output,'browser-failure.png'),fullPage:true}).catch(()=>{});
    throw error;
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
