const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium, webkit } = require(require.resolve('playwright', {
  paths: [process.env.PLAYWRIGHT_MODULE_PATH || path.resolve(__dirname, '../../../h5'), process.cwd()],
}));

const base = process.env.PROTOTYPE_URL || 'http://127.0.0.1:4178/';
const results = path.join(__dirname, 'results');
const checks = [];
const errors = [];
const external = new Set();
const screenshots = [];
const mark = (name) => { checks.push(name); console.log(`PASS ${name}`); };
let browser;

async function screenshot(page, name, phone = true) {
  const file = path.join(results, `${name}.png`);
  await page.locator('#toast').evaluate(el=>el.classList.remove('visible'));
  await (phone ? page.locator('#phone') : page).screenshot({ path: file, animations:'disabled', ...(phone ? {} : {fullPage:true}) });
  screenshots.push(path.basename(file));
}
async function expectNoOverflow(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'page overflows viewport');
  const overflow = await page.locator('.screen-content').evaluate(el => el.scrollWidth > el.clientWidth + 1);
  assert.equal(overflow, false, 'phone content overflows');
}
async function selectScreen(page, name) {
  await page.locator(`[data-screen="${name}"]`).click();
}
async function login(page) {
  await page.locator('#login-input').fill('demo@vireal.example');
  await page.locator('#login-form button[type=submit]').click();
  await page.locator('#login-input').fill('000000');
  await page.locator('#login-form button[type=submit]').click();
  assert.match(await page.locator('#login-error').textContent(), /不正确/);
  await page.locator('#login-input').fill('123456');
  await page.locator('#login-form button[type=submit]').click();
}

(async () => {
  await fs.mkdir(results, {recursive:true});
  browser = await chromium.launch({headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1080},acceptDownloads:true});
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith(new URL(base).origin) && !/^(data|blob):/.test(request.url())) external.add(request.url()); });
  const response = await page.goto(base);
  assert.equal(response.status(),200);
  assert.equal(await page.locator('.effect-card').count(),6);
  assert.match(await page.locator('.coin-pill').textContent(),/—/);
  await screenshot(page,'01-discover');
  await screenshot(page,'00-design-workbench',false);
  mark('游客目录、六种效果与演示标识');

  await page.locator('[data-action=category][data-id=romance]').click();
  assert.equal(await page.locator('.effect-card').count(),1);
  await page.locator('.effect-card').click();
  assert.match(await page.locator('.meta-row').textContent(),/2 张照片/);
  await page.locator('[data-action=use-effect]').click();
  assert.equal(await page.locator('#login-form').count(),1);
  await screenshot(page,'02-login');
  await login(page);
  assert.equal(await page.locator('.upload-tile').count(),2);
  assert.equal(await page.locator('[data-action=confirm-generate]').isDisabled(),true);
  await page.locator('[data-action=demo-photo]').click();
  await page.locator('[data-action=remove-photo][data-index="1"]').click();
  await page.locator('#photo-consent').check();
  assert.equal(await page.locator('[data-action=confirm-generate]').isDisabled(),true);
  await page.locator('[data-action=demo-photo]').click();
  await page.locator('#photo-consent').check();
  assert.equal(await page.locator('[data-action=confirm-generate]').isDisabled(),false);
  await screenshot(page,'03-two-photo-create');
  mark('邮箱错误与正确验证码、登录接续双图效果、缺图及授权校验');

  await selectScreen(page,'home');
  await page.locator('[data-action=category][data-id=all]').click();
  await page.locator('[data-action=effect][data-effect=dance-1]').click();
  await screenshot(page,'04-effect-detail');
  await page.locator('[data-action=use-effect]').click();
  assert.equal(await page.locator('.upload-tile').count(),1);
  // Use an actual PNG file to exercise browser-local decoding and replacement.
  const png = await page.locator('#phone').screenshot();
  await page.locator('input[data-photo="0"]').setInputFiles({name:'local-photo.png',mimeType:'image/png',buffer:png});
  await page.locator('.upload-tile.has-photo img').waitFor();
  assert.equal(await page.locator('.upload-tile img').evaluate(img=>img.src.startsWith('blob:')),true);
  await page.locator('[data-action=demo-photo]').click();
  await page.locator('#photo-consent').check();
  await page.locator('[data-action=variant][data-id=dance-10]').click();
  assert.match(await page.locator('.cost-card').textContent(),/56/);
  await page.locator('[data-action=variant][data-id=dance-5]').click();
  assert.match(await page.locator('.cost-card').textContent(),/28/);
  await screenshot(page,'05-create');
  await page.locator('[data-action=confirm-generate]').click();
  await page.locator('#modal [data-action=modal-cancel]').click();
  assert.equal(await page.locator('#modal').evaluate(el=>el.open),false);
  await page.locator('[data-action=confirm-generate]').click();
  await page.locator('#modal [data-action=modal-confirm]').click();
  await screenshot(page,'06-generation');
  await selectScreen(page,'create');
  await page.locator('[data-action=confirm-generate]').click();
  await selectScreen(page,'works');
  assert.equal(await page.locator('.work-card').count(),5);
  await selectScreen(page,'wallet');
  assert.match(await page.locator('.wallet-balance strong').textContent(),/100/);
  assert.equal(await page.locator('.ledger-row').count(),5);
  assert.equal(await page.locator('[data-action=recharge]').isDisabled(),true);
  await screenshot(page,'07-wallet');
  mark('本机文件预览、规格费用、确认取消、同草稿提交去重及演示余额');

  await selectScreen(page,'works');
  await page.locator('[data-action=filter][data-id=active]').click();
  assert.equal(await page.locator('.work-card').count(),1);
  await page.locator('[data-action=filter][data-id=all]').click();
  await page.locator('.work-card').first().click();
  await page.locator('[data-action=view-result]').waitFor({timeout:16000});
  await page.locator('[data-action=view-result]').click();
  await page.locator('video').evaluate(video=>new Promise((resolve,reject)=>{if(video.readyState>=1)return resolve();video.onloadedmetadata=()=>resolve();video.onerror=()=>reject(Error('demo media failed'));}));
  assert.ok(await page.locator('video').evaluate(video=>video.duration>4));
  await page.locator('video').evaluate(video=>video.play());
  await page.waitForFunction(()=>document.querySelector('#app video')?.currentTime>0.4);
  await page.locator('video').evaluate(video=>video.pause());
  const downloadWait=page.waitForEvent('download');
  await page.locator('[data-action=save-video]').click();
  const download=await downloadWait;
  assert.equal(download.suggestedFilename(),'vireal-demo.mp4');
  assert.ok((await fs.stat(await download.path())).size>1000);
  await screenshot(page,'08-result');
  await page.locator('[data-action=share-video]').click();
  assert.match(await page.locator('#modal').textContent(),/系统分享面板/);
  await page.keyboard.press('Escape');
  await page.locator('[data-action=delete-task]').click();
  await page.locator('#modal [data-action=modal-confirm]').click();
  assert.equal(await page.locator('.work-card').count(),4);
  mark('离页任务完成、作品筛选、可播放本地视频、实际文件下载及确认删除');

  await selectScreen(page,'settings');
  await page.locator('[data-action=edit-nickname]').click();
  await page.locator('#nickname').fill('  ');
  await page.locator('#modal [data-action=modal-confirm]').click();
  assert.equal(await page.locator('#modal').evaluate(el=>el.open),true);
  assert.match(await page.locator('#nickname-error').textContent(),/不能为空/);
  await page.locator('#nickname').fill('我的灵感');
  await page.locator('#modal [data-action=modal-confirm]').click();
  await selectScreen(page,'account');
  assert.match(await page.locator('.profile-hero h3').textContent(),/我的灵感/);
  await screenshot(page,'09-account');
  await selectScreen(page,'settings');
  await page.locator('[data-action=switch-account]').click();
  assert.match(await page.locator('.wallet-teaser .balance').textContent(),/0/);
  await page.locator('.tabbar [data-route=works]').click();
  assert.equal(await page.locator('.work-card').count(),0);
  assert.match(await page.locator('.empty-state h3').textContent(),/还没有作品/);
  await selectScreen(page,'settings');
  await page.locator('[data-action=logout]').click();
  await page.locator('#modal [data-action=modal-confirm]').click();
  await page.locator('.tabbar [data-route=works]').click();
  assert.equal(await page.locator('.work-card').count(),0);
  assert.equal(await page.locator('[data-action=login-works]').count(),1);
  mark('昵称校验、换账户数据隔离与退出后的游客作品页');

  await page.locator('#reset-demo').click();
  for(const scenario of ['loading','empty','offline','closed','lowbalance','quota','removed','authExpired','unknown','failed','expired']){
    await page.locator('#scenario').selectOption(scenario);
    await expectNoOverflow(page);
    if(['closed','lowbalance','quota','removed'].includes(scenario))assert.equal(await page.locator('#app .primary').first().isDisabled(),true);
    if(scenario==='unknown'){
      const before=await page.locator('.task-facts').textContent();
      await page.locator('[data-action=query-task]').click();
      assert.equal(await page.locator('.task-facts').textContent(),before);
      await screenshot(page,'10-submission-unknown');
    }
    if(scenario==='expired'){
      assert.equal(await page.locator('#app video,[data-action=save-video],[data-action=share-video]').count(),0);
      await screenshot(page,'11-expired');
    }
  }
  mark('全部异常状态可达、关闭场景禁用提交、待确认不重开、过期媒体无操作');

  await page.locator('#scenario').selectOption('normal');
  for(const width of [375,393,430]){
    await page.setViewportSize({width,height:852});
    for(const name of ['home','detail','login','create','task','works','result','account','wallet','settings']){
      await selectScreen(page,name);await expectNoOverflow(page);
    }
    await selectScreen(page,'home');
    if(width===393)await screenshot(page,'12-mobile',false);
  }
  mark('375、393、430 点宽下全部主要页面无横向溢出');

  await page.emulateMedia({reducedMotion:'reduce'});
  await page.locator('#scenario').selectOption('unknown');
  await selectScreen(page,'task');
  assert.equal(await page.locator('.progress-orbit').evaluate(el=>getComputedStyle(el,'::before').animationName),'none');
  await page.setViewportSize({width:1440,height:1080});
  await page.locator('#reset-demo').click();
  assert.equal(external.size,0,`external requests: ${[...external]}`);
  assert.deepEqual(errors,[]);
  for(const filename of ['DESIGN.md','API.md','ACCEPTANCE.md','design-tokens.json']){
    assert.equal((await context.request.get(new URL(filename,base).href)).status(),200);
  }
  const csp=await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
  assert.match(csp,/connect-src 'none'/);
  mark('减少动态效果、交接文件、无页面错误、无外部请求与禁止脚本联网');

  await context.close();await browser.close();browser=null;
  // Safari engine is useful for the intended iPhone audience, not just Chromium.
  const safari=await webkit.launch({headless:true});browser=safari;
  const safariPage=await safari.newPage({viewport:{width:393,height:852}});
  await safariPage.goto(base);
  assert.equal(await safariPage.locator('.effect-card').count(),6);
  await selectScreen(safariPage,'create');
  await safariPage.locator('[data-action=demo-photo]').click();
  await safariPage.locator('#photo-consent').check();
  assert.equal(await safariPage.locator('[data-action=confirm-generate]').isDisabled(),false);
  await safariPage.locator('[data-action=confirm-generate]').click();
  assert.equal(await safariPage.locator('#modal').evaluate(el=>el.open),true);
  await expectNoOverflow(safariPage);
  await safari.close();browser=null;
  mark('Safari 引擎下目录、选图、授权和生成确认可用');
  const directBrowser=await chromium.launch({headless:true});browser=directBrowser;
  const directPage=await directBrowser.newPage();
  await directPage.goto(new URL(`file://${path.resolve(__dirname,'../index.html')}`).href);
  assert.equal(await directPage.locator('.effect-card').count(),6);
  await directPage.locator('[data-action=effect]').first().click();
  assert.equal(await directPage.locator('[data-action=use-effect]').count(),1);
  await directBrowser.close();browser=null;
  mark('直接打开本地 HTML 可浏览与操作');
  await fs.writeFile(path.join(results,'summary.json'),JSON.stringify({status:'passed',checkedAt:new Date().toISOString(),base,checks,screenshots,externalRequests:[...external],pageErrors:errors,limits:['仅原型验证，不代表真机或线上服务验收','原生 SDK、VoiceOver、相册权限及真实生成待单独验证']},null,2));
  console.log(`Verified ${checks.length} groups. Results: ${results}`);
})().catch(async error=>{
  console.error(error);
  await fs.mkdir(results,{recursive:true});
  await fs.writeFile(path.join(results,'summary.json'),JSON.stringify({status:'failed',checks,error:String(error),pageErrors:errors},null,2));
  if(browser)await browser.close();process.exitCode=1;
});
