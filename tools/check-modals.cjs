/**
 * Proves the native confirm/alert/prompt are gone and the custom dialog works.
 *
 * Key assertion: Playwright auto-dismisses NATIVE dialogs by default. So if the
 * page still used window.confirm, clicking delete would produce no modal at all
 * and every check below would fail. That makes this a real test, not a rubber stamp.
 *
 * Usage: NODE_PATH=<pw-harness>/node_modules WORTHLESSTASK_TEST_URL=http://127.0.0.1:PORT \
 *        WORTHLESSTASK_TEST_BROWSER=<chrome> node tools/check-modals.cjs
 */
const { chromium } = require('playwright');

const base = process.env.WORTHLESSTASK_TEST_URL || 'http://127.0.0.1:8787';
const executablePath = process.env.WORTHLESSTASK_TEST_BROWSER;

const results = [];
const check = (name, pass, detail = '') => {
  results.push({ name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
};

(async () => {
  const browser = await chromium.launch({
    executablePath,
    // 127.0.0.1 must never go through a proxy; without this the loopback can 502.
    args: ['--no-sandbox', '--no-proxy-server', '--proxy-bypass-list=<-loopback>'],
  });
  const page = await browser.newPage({ viewport: { width: 1380, height: 900 } });

  const pageErrors = [];
  let nativeDialog = null;
  page.on('pageerror', e => pageErrors.push(String(e)));
  // If a native dialog fires we record it (and Playwright dismisses it).
  page.on('dialog', async d => { nativeDialog = { type: d.type(), message: d.message() }; await d.dismiss(); });

  await page.goto(base, { waitUntil: 'networkidle' });

  // --- go to the games view, where the delete buttons live
  await page.click('#tabPlay');
  await page.waitForSelector('#games .game', { timeout: 15000 });

  const gamesBefore = await page.locator('#games .game').count();
  check('library has games to act on', gamesBefore > 0, `${gamesBefore} games`);

  // --- open the delete dialog
  await page.locator('#games .game [data-act="delete"]').first().click();

  const scrim = page.locator('#modalRoot');
  const appeared = await scrim.isVisible().catch(() => false);
  check('custom modal opens on delete click', appeared === true,
    appeared ? '' : 'modal did not appear — native confirm may still be in use');
  check('no native dialog fired', nativeDialog === null,
    nativeDialog ? `native ${nativeDialog.type}: ${nativeDialog.message}` : '');

  if (!appeared) {
    console.log('\nABORT: modal never appeared; remaining checks cannot run.');
    console.log(JSON.stringify({ passed: results.filter(r => r.pass).length, results }, null, 2));
    await browser.close();
    process.exit(1);
  }

  // --- content
  const title = (await page.locator('#modalTitle').textContent()) || '';
  const msg = (await page.locator('#modalMsg').textContent()) || '';
  const okText = (await page.locator('#modalOk').textContent()) || '';
  const cancelText = (await page.locator('#modalCancel').textContent()) || '';

  check('title is "Удалить игру?"', title.includes('Удалить игру'), JSON.stringify(title));
  check('message matches spec', msg.includes('Файлы установленной игры не затрагиваются'), JSON.stringify(msg.slice(0, 60)));
  check('confirm button reads "Удалить"', okText.includes('Удалить'), JSON.stringify(okText));
  check('cancel button reads "Отмена"', cancelText.includes('Отмена'), JSON.stringify(cancelText));

  // --- semantics: danger styling + default focus on cancel
  const okClass = (await page.locator('#modalOk').getAttribute('class')) || '';
  check('confirm button carries danger styling', okClass.includes('danger'), okClass);

  const focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
  check('default focus is on cancel', focused === 'modalCancel', `focus=${focused}`);

  // --- accessibility
  const aria = await page.evaluate(() => {
    const d = document.querySelector('#modalRoot .modal');
    return d ? { role: d.getAttribute('role'), modal: d.getAttribute('aria-modal'),
                 labelledby: d.getAttribute('aria-labelledby'), describedby: d.getAttribute('aria-describedby') } : null;
  });
  check('role="dialog"', aria && aria.role === 'dialog', JSON.stringify(aria));
  check('aria-modal="true"', aria && aria.modal === 'true');
  check('aria-labelledby -> title', aria && aria.labelledby === 'modalTitle');
  check('aria-describedby -> message', aria && aria.describedby === 'modalMsg');

  // --- scroll locked while open
  const locked = await page.evaluate(() => document.documentElement.style.overflow === 'hidden');
  check('page scroll is locked', locked === true);

  // --- Escape cancels
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  const afterEsc = await scrim.isVisible().catch(() => false);
  check('Escape closes the dialog', afterEsc === false);
  const afterEscGames = await page.locator('#games .game').count();
  check('Escape counts as cancel (nothing deleted)', afterEscGames === gamesBefore,
    `${gamesBefore} -> ${afterEscGames}`);
  const unlocked = await page.evaluate(() => document.documentElement.style.overflow === '');
  check('scroll lock released', unlocked === true);

  // --- backdrop click cancels
  await page.locator('#games .game [data-act="delete"]').first().click();
  await page.waitForTimeout(350);
  const box = await scrim.boundingBox();
  await page.mouse.down({ x: box.x + 8, y: box.y + 8 });
  await page.mouse.up({ x: box.x + 8, y: box.y + 8 });
  await page.waitForTimeout(400);
  const afterBackdrop = await scrim.isVisible().catch(() => false);
  const afterBackdropGames = await page.locator('#games .game').count();
  check('backdrop click cancels', afterBackdrop === false);
  check('backdrop cancel deletes nothing', afterBackdropGames === gamesBefore);

  // --- confirming resolves true (exercised directly so we never delete a real game)
  const confirmed = await page.evaluate(async () => {
    const p = window.__showConfirm
      ? window.__showConfirm({ title: 'T', message: 'M', confirmText: 'OK', cancelText: 'No' })
      : null;
    if (!p) return 'no-hook';
    setTimeout(() => document.getElementById('modalOk').click(), 60);
    return await p;
  });
  // Without a hook we verify through the real button instead.
  if (confirmed === 'no-hook' || confirmed === null) {
    await page.locator('#games .game [data-act="delete"]').first().click();
    await page.waitForTimeout(350);
    const okVisible = await page.locator('#modalOk').isVisible();
    check('confirm button is reachable and clickable', okVisible === true);
    // Cancel out — do not actually delete dj's library.
    await page.locator('#modalCancel').click();
    await page.waitForTimeout(400);
  } else {
    check('confirming resolves true', confirmed === true, String(confirmed));
  }

  const finalGames = await page.locator('#games .game').count();
  check('library intact after all dialog interaction', finalGames === gamesBefore,
    `${gamesBefore} -> ${finalGames}`);

  // --- narrow viewport
  await page.setViewportSize({ width: 380, height: 780 });
  await page.locator('#games .game [data-act="delete"]').first().click();
  await page.waitForTimeout(350);
  const narrowOk = await page.locator('#modalRoot .modal').boundingBox();
  check('modal fits a 380px viewport', narrowOk && narrowOk.width <= 380,
    narrowOk ? `${Math.round(narrowOk.width)}px wide` : 'no modal');
  await page.keyboard.press('Escape');

  check('no page errors', pageErrors.length === 0, pageErrors.join(' | ').slice(0, 300));

  await browser.close();

  const passed = results.filter(r => r.pass).length;
  console.log(`\n${passed}/${results.length} checks passed`);
  process.exit(passed === results.length ? 0 : 1);
})().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
