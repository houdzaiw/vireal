(() => {
  'use strict';

  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const icons = {
    discover:'<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7L12 3Z"/>',
    works:'<rect x="4" y="3" width="16" height="18" rx="4"/><path d="m10 8 6 4-6 4V8Z"/>',
    person:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    back:'<path d="m14 5-7 7 7 7"/>', right:'<path d="m9 6 6 6-6 6"/>',
    play:'<path d="m9 5 10 7-10 7V5Z"/>', plus:'<path d="M12 5v14M5 12h14"/>',
    image:'<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
    close:'<path d="m6 6 12 12M6 18 18 6"/>', check:'<path d="m5 12 4 4L19 6"/>',
    shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v.1"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    wallet:'<path d="M20 8H5a2 2 0 0 1 0-4h13v4"/><path d="M3 6v12a2 2 0 0 0 2 2h15V8M20 12h-5v4h5"/>',
    download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    share:'<path d="M12 16V3m-5 5 5-5 5 5M5 12H3v9h18v-9h-2"/>',
    trash:'<path d="M3 6h18M8 6V3h8v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
    settings:'<path d="m9 3-1 3-3 1-2 5 2 5 3 1 1 3h6l1-3 3-1 2-5-2-5-3-1-1-3H9Z"/><circle cx="12" cy="12" r="3"/>',
    help:'<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4M12 17v.1"/>',
    logout:'<path d="M10 4H4v16h6M9 12h12m-5-5 5 5-5 5"/>',
    network:'<path d="m3 3 18 18M8 8a10 10 0 0 1 13 2M3 10l2-2M6 14a7 7 0 0 1 3-2m4 0a7 7 0 0 1 5 2M9 17l3-2 3 2M12 21v-.1"/>',
    refresh:'<path d="M20 10a8 8 0 1 0 0 5M20 3v7h-7"/>',
  };
  const icon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.discover}</svg>`;
  const categories = [
    {id:'all', title:'精选'}, {id:'kiss',title:'亲吻'}, {id:'romance',title:'浪漫'},
    {id:'charm',title:'魅力'}, {id:'outfit',title:'换装'}, {id:'dance',title:'舞蹈'}, {id:'anime',title:'动漫'},
  ];
  const effects = [
    {id:'dance-1',title:'随光起舞',en:'DANCE WITH LIGHT',category:'dance',count:1,num:'01',tone:'#234957',glow:'#75c9df80',description:'让静止的瞬间，拥有自己的节奏。上传一张清晰照片，开启一段随光而动的影像。',variants:[{id:'dance-5',duration:5,cost:28},{id:'dance-10',duration:10,cost:56}]},
    {id:'romance-1',title:'浪漫相拥',en:'A MOMENT TOGETHER',category:'romance',count:2,num:'02',tone:'#563449',glow:'#da8db980',description:'让两个人的照片，成为同一个温柔瞬间。请分别添加两位已授权人物的照片。',variants:[{id:'romance-5',duration:5,cost:36},{id:'romance-10',duration:10,cost:72}]},
    {id:'anime-1',title:'次元漫游',en:'ANOTHER DIMENSION',category:'anime',count:1,num:'03',tone:'#3e366c',glow:'#ac99ed80',description:'保留你的神情，走进另一种画风。一张照片，开启一段梦幻的动漫旅程。',variants:[{id:'anime-5',duration:5,cost:32}]},
    {id:'kiss-1',title:'心动一刻',en:'CLOSER TO YOU',category:'kiss',count:2,num:'04',tone:'#623847',glow:'#e9a1a280',description:'记录两个人靠近的心动瞬间。需要分别添加两位已授权人物的清晰照片。',variants:[{id:'kiss-5',duration:5,cost:36}]},
    {id:'outfit-1',title:'风格切换',en:'YOUR NEXT LOOK',category:'outfit',count:1,num:'05',tone:'#4e5140',glow:'#d0d2a380',description:'换一种风格，发现另一面的自己。上传一张人物照片，体验服装风格的动态变化。',variants:[{id:'outfit-5',duration:5,cost:28},{id:'outfit-10',duration:10,cost:56}]},
    {id:'charm-1',title:'光影肖像',en:'IN YOUR OWN LIGHT',category:'charm',count:1,num:'06',tone:'#374e4e',glow:'#9ddaca80',description:'让细微的表情和流动的光影，为你的肖像增添生命力。',variants:[{id:'charm-5',duration:5,cost:28}]},
  ];
  const pages = {
    home:{title:'发现',symbol:'discover',description:'延续网页的深色视觉与效果分类，让灵感先于登录发生。',points:['游客可浏览；创作时再登录。','分类和卡片顺序由后台决定。','此处采用品牌渐变占位图，不冒充真实效果。'],apis:[['GET','/effect-catalog']]},
    detail:{title:'效果详情',symbol:'play',description:'先看效果，再了解需要几张照片、支持的时长与金币消耗。',points:['大幅预览承载效果内容。','底部主操作固定，单手容易触达。','下架或服务关闭时明确说明原因。'],apis:[['GET','/effects/{slug}'],['GET','/paypal/config']]},
    login:{title:'邮箱登录',symbol:'shield',description:'登录后接续刚才的创作意图，沿用网页已有的 Clerk 身份。',points:['首版沿用邮箱验证，不增加社交登录。','身份验证与业务会话初始化分两步。','验证码 123456 只用于本地交互演示。'],apis:[['POST','/auth/session']]},
    create:{title:'创建视频',symbol:'image',description:'照片、时长和费用在同一页完成确认，避免来回跳转。',points:['一张或两张照片由效果配置决定。','只展示该效果实际支持的时长。','提交按钮校验照片、授权、金币及服务状态。'],apis:[['POST','/uploads/images'],['POST','/video-tasks'],['GET','/wallet']]},
    task:{title:'生成进度',symbol:'clock',description:'明确当前任务处于哪一步，用户可以离开页面稍后回来。',points:['不编造生成百分比或完成时间。','超时或提交状态未知时不重复创建。','返回前台查询同一任务。'],apis:[['GET','/video-tasks/{id}']]},
    works:{title:'我的作品',symbol:'works',description:'任务和成品统一在账户作品中，不让进行中的视频失去入口。',points:['按全部、进行中、已完成筛选。','失败、待确认及过期均有文字状态。','换账户后清除上个账户的页面数据。'],apis:[['GET','/video-tasks?skip=0&limit=50']]},
    result:{title:'作品详情',symbol:'play',description:'观看、保存、分享各有明确入口，同时说明媒体保留期限。',points:['本地片段用于演示播放器与下载。','真实客户端保存到相册，调用系统分享。','删除需确认；进行中的任务不能删除。'],apis:[['GET','/video-tasks/{id}'],['GET','/video-tasks/{id}/download'],['DELETE','/video-tasks/{id}']]},
    account:{title:'我的',symbol:'person',description:'把账户、金币和帮助集中在一起，保持三栏主导航简单。',points:['金币显示服务端账户余额。','访客可查看说明，登录后看个人内容。','充值首版保持关闭。'],apis:[['GET','/users/me'],['GET','/wallet']]},
    wallet:{title:'金币明细',symbol:'wallet',description:'解释金币的使用与变动，不在内测版引入尚未就绪的充值。',points:['余额、额度和流水来自服务端。','失败是否退币以流水和任务字段为准。','演示余额和价格不用于真实购买。'],apis:[['GET','/wallet'],['GET','/orders']]},
    settings:{title:'账户设置',symbol:'settings',description:'保留轻量的资料管理和明确的当前会话退出操作。',points:['首版只修改昵称，不引入头像上传链路。','退出当前 App 会话，不退出其他设备。','账户注销属于上架前需补齐的服务端能力。'],apis:[['PATCH','/users/me'],['POST','/auth/logout']]},
    legal:{title:'使用说明',symbol:'help',description:'用易懂的语言说明照片处理、金币与作品有效期。',points:['原型说明不替代上线隐私政策。','在用户选照片、提交和保存时给出相关提示。','真实保留期限读取后端配置。'],apis:[['GET','/configs']]},
  };
  const scenarioHelp = {
    normal:'可完整体验浏览、模拟登录、选图、生成和保存。',loading:'预览加载占位；点击“完成加载”恢复当前页面。',
    empty:'预览目录、作品或流水为空的情况。',offline:'保留当前页面意图；恢复网络后可继续。',closed:'预览服务关闭，仍可浏览效果和历史记录。',
    lowbalance:'演示可用余额 5 金币，生成入口暂停。',quota:'演示今日生成额度为零，充值也不会解除限制。',removed:'预览效果下架，返回发现选择其他效果。',
    authExpired:'清除本地演示会话并显示重新登录入口。',unknown:'任务提交结果待确认，只查询原任务，不重新生成。',failed:'预览生成失败与已退币状态。',expired:'预览作品过期，播放、保存和分享不可用。',
  };
  const defaultEmail = 'demo@vireal.example';
  const state = {
    screen:'home',history:[],category:'all',effectId:'dance-1',variantId:'dance-5',scenario:'normal',
    userKey:null,users:new Map(),uploads:[],authorized:false,selectedTask:null,filter:'all',
    loginStage:'email',loginEmail:defaultEmail,loginError:'',returnScreen:'create',legalKind:'guide',submission:null,
  };
  let toastTimer;
  let modalAction = null;
  let photoEpoch = 0;
  const photoRequests = new Map();
  let renderedScreen = null;
  const uid = () => globalThis.crypto?.randomUUID?.() || `demo-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  function user() { return state.users.get(state.userKey) || null; }
  function seedUser(email) {
    const key = email.trim().toLowerCase();
    if (!state.users.has(key)) {
      const initial = key === defaultEmail;
      state.users.set(key, {id:uid(),email:key,nickname:initial?'灵感创作者':'新创作者',balance:initial?128:0,tasks:initial?[
        {id:'demo-completed',effectId:'dance-1',variantId:'dance-5',status:'succeeded',createdAt:Date.now()-3600000,cost:28,duration:5},
        {id:'demo-romance',effectId:'romance-1',variantId:'romance-5',status:'succeeded',createdAt:Date.now()-86400000,cost:36,duration:5},
        {id:'demo-failed',effectId:'anime-1',variantId:'anime-5',status:'failed',refunded:true,createdAt:Date.now()-172800000,cost:32,duration:5},
        {id:'demo-expired',effectId:'outfit-1',variantId:'outfit-5',status:'expired',createdAt:Date.now()-604800000,cost:28,duration:5},
      ]:[],ledger:initial?[
        {reason:'随光起舞 · 5 秒',delta:-28,date:'今天 09:28'},
        {reason:'次元漫游 · 生成失败退回',delta:32,date:'11 月 19 日'},
        {reason:'次元漫游 · 5 秒',delta:-32,date:'11 月 19 日'},
        {reason:'内测演示余额',delta:156,date:'11 月 18 日'},
      ]:[]});
    }
    return key;
  }
  function ensureDemoUser() { if (!user()) state.userKey = seedUser(defaultEmail); }
  function currentEffect() { return effects.find(e=>e.id === state.effectId) || effects[0]; }
  function currentVariant() { return currentEffect().variants.find(v=>v.id === state.variantId) || currentEffect().variants[0]; }
  function balance() { return state.scenario === 'lowbalance' ? 5 : user()?.balance ?? 0; }
  function task() { return user()?.tasks.find(t=>t.id === state.selectedTask) || user()?.tasks[0] || null; }
  function taskStatus(t) { return ['unknown','failed','expired'].includes(state.scenario) ? ({unknown:'submission_unknown',failed:'failed',expired:'expired'}[state.scenario]) : t.status; }
  function clearUploads() { photoEpoch++;photoRequests.clear();state.uploads.forEach(p=>{if(p?.url?.startsWith('blob:'))URL.revokeObjectURL(p.url);});state.uploads=[];state.authorized=false;state.submission=null; }
  function chooseEffect(id) { if(state.effectId !== id){clearUploads();state.effectId=id;state.variantId=currentEffect().variants[0].id;} }
  function go(screen,{replace=false}={}) {
    if(!pages[screen])return;
    if(!replace && state.screen!==screen)state.history.push(state.screen);
    state.screen=screen;
    if(location.hash !== `#${screen}`)history.replaceState(null,'',`#${screen}`);
    render();
  }
  function back() { const previous=state.history.pop() || 'home';go(previous,{replace:true}); }
  function needLogin(destination) {
    if(user()){go(destination);return;}
    state.returnScreen=destination;state.loginStage='email';state.loginError='';go('login');
  }
  function toast(message) { $('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3200); }
  function art(effect,extra='') {
    return `<div class="art ${extra}" style="--tone:${effect.tone};--glow:${effect.glow}" aria-hidden="true"><span class="art-name">${effect.en}</span><span class="art-num">${effect.num}</span><span class="art-orb"></span></div>`;
  }
  function topbar(title,action='') { return `<header class="nav-bar"><button class="icon-button" data-action="back" aria-label="返回">${icon('back')}</button><h2>${esc(title)}</h2>${action||'<span></span>'}</header>`; }
  function tabs(active) { return `<nav class="tabbar" aria-label="App 主导航">${[['home','discover','发现'],['works','works','作品'],['account','person','我的']].map(([route,symbol,title])=>`<button class="${active===route?'active':''}" data-action="tab" data-route="${route}" ${active===route?'aria-current="page"':''}>${icon(symbol)}${title}</button>`).join('')}</nav>`; }
  function screen(content,{title='',active='',dock='',headerAction=''}={}) { return `<div class="screen ${active?'with-tabs':''}">${title?topbar(title,headerAction):''}<div class="screen-content" tabindex="-1">${content}</div>${dock}${active?tabs(active):''}</div>`; }
  function primary(label,action,disabled=false,extra='') { return `<button class="primary" data-action="${action}" ${disabled?'disabled':''} ${extra}>${label}</button>`; }
  function secondary(label,action,extra='') { return `<button class="secondary" data-action="${action}" ${extra}>${label}</button>`; }
  function notice(message,symbol='info') { return `<div class="notice" role="status">${icon(symbol)}<span>${message}</span></div>`; }
  function empty(title,copy,symbol='works',button='开始创作',action='home') { return `<div class="empty-state"><div class="empty-icon">${icon(symbol)}</div><h3>${title}</h3><p>${copy}</p>${button?secondary(button,action):''}</div>`; }
  function unavailable() {
    if(state.scenario==='closed')return '服务暂未开放，照片上传和生成暂不可用。';
    if(state.scenario==='removed')return '此效果已下架，请选择其他效果。';
    if(state.scenario==='quota')return '今日生成额度已用完，请在额度重置后再试。';
    return '';
  }
  function effectCard(effect,index) { return `<button class="effect-card ${index===0?'featured':''}" data-action="effect" data-effect="${effect.id}" aria-label="查看${effect.title}，需要${effect.count}张照片，${effect.variants[0].cost}金币起">${art(effect)}<span class="effect-play">${icon('play')}</span><div class="effect-caption"><span class="tiny">${effect.en}</span><h3>${effect.title}</h3><div class="card-bottom"><p>${effect.count} 张照片 · ${effect.variants[0].duration} 秒起</p><span class="tag">✦ ${effect.variants[0].cost} 起</span></div></div></button>`; }
  function homePage() {
    const shown=state.scenario==='empty'?[]:effects.filter(e=>state.category==='all'||e.category===state.category);
    return screen(`<header class="screen-heading"><div><span class="app-brand">VIREAL ✦</span><div class="demo-label">AI VIDEO · 交互演示</div></div><button class="coin-pill" data-action="wallet" aria-label="查看金币"><span class="coin">✦</span> ${user()?balance():'—'}</button></header><div class="category-strip" aria-label="效果分类">${categories.map(c=>`<button data-action="category" data-id="${c.id}" class="${c.id===state.category?'selected':''}" aria-pressed="${c.id===state.category}">${c.title}</button>`).join('')}</div><div class="hero-copy"><span class="eyebrow">BECOME YOUR NEXT</span><h2>找到你的下一种<br><em>可能性。</em></h2></div>${state.scenario==='closed'?notice('当前仅供浏览，创作服务暂未开放。'):''}${shown.length?`<div class="effect-grid">${shown.map(effectCard).join('')}</div>`:empty('灵感正在准备中','这个分类暂时没有效果，试试其他分类。','discover','查看精选','all-category')}<p class="app-note">${icon('info')}<span>效果、费用和余额均为演示。渐变封面用于展示媒体缺失时的品牌占位效果。</span></p>`,{active:'home'});
  }
  function detailPage() {
    const e=currentEffect();const blocked=unavailable();
    return screen(`<div class="detail-visual">${art(e)}<button class="preview-control" data-action="preview-video" aria-label="播放演示片段"><span class="round-play">${icon('play')}</span></button><div class="preview-caption"><span>效果预览 · 演示片段</span><span>${e.variants[0].duration}s</span></div></div><h1 class="detail-title">${e.title}</h1><p class="body-copy">${e.description}</p><div class="meta-row"><span class="meta-chip">${e.count} 张照片</span><span class="meta-chip">${e.variants.map(v=>v.duration).join(' / ')} 秒</span><span class="meta-chip">✦ ${e.variants[0].cost} 金币起</span></div><div class="info-card"><h3>准备好你的照片</h3><p>使用清晰、无遮挡的人物照片。请确认你有权使用照片，并已获得照片中人物的同意。</p></div>`,{title:'效果详情',dock:`<div class="action-dock">${blocked?`<p class="blocking-note">${blocked}</p>`:`<div class="dock-note"><span>${e.count} 张照片，开启创作</span><span>✦ ${e.variants[0].cost} 起</span></div>`}${primary(blocked?'暂不可使用':'使用此效果','use-effect',Boolean(blocked))}${blocked?'<button class="text-button" data-action="home">返回发现</button>':''}</div>`});
  }
  function loginPage() {
    const codeStage=state.loginStage==='code';
    return screen(`<div class="login-spark">✦</div><h1 class="login-title">${codeStage?'查看你的邮箱':'让每一次灵感，'}${codeStage?'':'<br>都有迹可循。'}</h1><p class="body-copy">${codeStage?`正在为 <strong>${esc(state.loginEmail)}</strong> 验证登录。`:'登录 Vireal，让作品与金币跟随你的账户。'}</p><form id="login-form" data-form="login"><div class="form-group"><label for="login-input">${codeStage?'邮箱验证码':'邮箱地址'}</label><input id="login-input" name="${codeStage?'code':'email'}" type="${codeStage?'text':'email'}" ${codeStage?'inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" placeholder="输入 6 位演示验证码"':`autocomplete="email" value="${esc(state.loginEmail)}" placeholder="输入邮箱地址"`} required></div><div class="form-error" id="login-error" role="alert">${esc(state.loginError)}</div><button class="primary" type="submit">${codeStage?'验证并继续':'继续'}</button></form><p class="local-note">${codeStage?'演示验证码：<strong>123456</strong>。没有发送邮件，也不会验证真实账户。':'本地交互演示，不会发送邮件。请使用示例邮箱，无需填写真实信息。'}</p>${codeStage?'<button class="text-button" data-action="change-email">更换邮箱</button>':''}<div class="login-terms">继续即表示你了解本次为原型体验。<br><button data-action="legal" data-kind="terms">服务说明</button> · <button data-action="legal" data-kind="privacy">隐私说明</button></div>`,{title:codeStage?'邮箱验证':'登录 Vireal'});
  }
  function createPage() {
    if(!user())return loginPage();
    const e=currentEffect(),v=currentVariant();const blocked=unavailable()||(balance()<v.cost?'金币不足，充值暂未开放。':'');
    const photosReady=Array.from({length:e.count},(_,i)=>state.uploads[i]).every(Boolean);
    if(state.submission){
      return screen(`<div class="info-card"><h3>这次创作已提交</h3><p>你可以查看原任务的进度。再次使用此效果会开启一份新的创作草稿。</p></div>`,{title:'创建视频',dock:`<div class="action-dock">${primary('查看已提交任务','confirm-generate')}<button class="text-button" data-action="new-creation">再次使用此效果</button></div>`});
    }
    return screen(`<div class="effect-summary"><div class="mini-art">${art(e)}</div><div><h3>${e.title}</h3><p>${e.count} 张照片 · AI 动态效果</p></div></div><div class="field-title"><h3>添加照片</h3><span>${state.uploads.filter(Boolean).length} / ${e.count}</span></div><div class="upload-grid" style="--count:${e.count}">${Array.from({length:e.count},(_,i)=>`<div class="upload-tile ${state.uploads[i]?'has-photo':''}">${state.uploads[i]?`<img src="${esc(state.uploads[i].url)}" alt="本机选择的第 ${i+1} 张照片"><button class="remove-photo" data-action="remove-photo" data-index="${i}" aria-label="移除第 ${i+1} 张照片">${icon('close')}</button>`:''}<button data-action="choose-photo" data-index="${i}" aria-label="${state.uploads[i]?'替换':'添加'}第 ${i+1} 张照片">${state.uploads[i]?'':`${icon('plus')}<span>${e.count===1?'选择一张照片':`人物 ${i+1}`}</span>`}</button><input class="sr-only" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" data-photo="${i}" aria-label="选择第 ${i+1} 张照片文件" tabindex="-1"></div>`).join('')}</div><p class="upload-tip">请选择清晰、无遮挡的照片。此原型仅在本机预览；真实客户端会在你确认后上传。</p><button class="text-button demo-photo" data-action="demo-photo">使用演示图片</button><div class="field-title"><h3>视频时长</h3><span>按可用规格选择</span></div><div class="duration-row">${e.variants.map(o=>`<button class="duration ${o.id===v.id?'selected':''}" data-action="variant" data-id="${o.id}" aria-pressed="${o.id===v.id}"><strong>${o.duration} 秒</strong><small>✦ ${o.cost} 金币</small></button>`).join('')}</div><div class="cost-card"><span>本次消耗</span><strong>✦ ${v.cost}</strong></div><label class="consent"><input type="checkbox" id="photo-consent" ${state.authorized?'checked':''}><span>我有权使用所选照片，并已获得照片中人物的同意。</span></label>${blocked?notice(blocked):''}`,{title:'创建视频',dock:`<div class="action-dock"><div class="dock-note"><span>可用金币 <b>${balance()}</b></span><span>内测 · 充值暂未开放</span></div>${primary(`生成视频 · ✦ ${v.cost}`,'confirm-generate',Boolean(blocked)||!photosReady||!state.authorized)}<p class="upload-tip">原型模拟生成，不会扣除真实金币或调用模型。</p></div>`});
  }
  const statusLabels={submitting:'正在提交',pending:'等待生成',running:'正在生成',rendering_demo:'正在生成演示',saving:'正在保存',succeeded:'已完成',failed:'生成失败',canceled:'已取消',submission_unknown:'正在确认',expired:'已过期'};
  function taskPage() {
    const t=task();if(!t)return screen(empty('还没有生成任务','先选择一个效果，开始你的创作。','clock'),{title:'生成进度'});
    const status=taskStatus(t),e=effects.find(e=>e.id===t.effectId)||effects[0];
    if(['expired','canceled'].includes(status))return screen(empty(status==='expired'?'这件作品已过期':'任务已取消',status==='expired'?'媒体保存期限已结束，仍可查看历史记录。':'金币处理结果请查看账户明细。','clock','返回作品','works'),{title:'任务详情'});
    const unknown=status==='submission_unknown',failed=status==='failed',done=status==='succeeded';
    const stage=['submitting','pending'].includes(status)?0:status==='saving'?2:1;
    const heading=unknown?'正在确认提交结果':failed?'这次生成未完成':done?'你的作品，已准备好':'灵感正在变成影像';
    const copy=unknown?'暂时无法确认结果，请稍后查询原任务。<br>不要重复提交。':failed?(t.refunded||state.scenario==='failed'?'本次演示任务已退回金币。<br>真实退币结果以账户流水为准。':'退币状态正在核对，请查看金币明细。'):done?'可以前往作品详情播放或保存。':'你可以离开此页。<br>稍后在「作品」里查看结果。';
    return screen(`<div class="task-stage">${done?`<div class="success-mark">${icon('check')}</div>`:`<div class="progress-orbit"><span>${unknown?'?':failed?'!':'✦'}</span></div>`}<h3>${heading}</h3><p>${copy}</p></div>${!unknown&&!failed&&!done?`<div class="steps">${[['任务已提交','你的照片已就绪'],['AI 生成中','根据所选效果生成影像'],['保存作品','完成后可播放与下载']].map(([label,copy],i)=>`<div class="step ${i<stage?'complete':i===stage?'current':''}"><span class="step-icon">${i<stage?'✓':i+1}</span><div>${label}<div class="caption muted">${copy}</div></div></div>`).join('')}</div>`:''}<div class="info-card"><div class="effect-summary" style="margin:0"><div class="mini-art">${art(e)}</div><div><h3>${e.title}</h3><p>${t.duration} 秒 · ${t.cost} 金币</p></div></div></div><div class="task-facts"><div><span>任务状态</span><b>${statusLabels[status]}</b></div><div><span>演示任务编号</span><b>${esc(t.id.slice(-12))}</b></div><div><span>金币处理</span><b>${failed?'请以金币明细为准':`${t.cost} 金币`}</b></div></div>${!unknown&&!failed&&!done?'<p class="local-note">演示任务约 12 秒完成，流程时间不代表真实生成耗时。</p>':''}`,{title:'生成进度',dock:`<div class="action-dock">${done?primary('查看作品','view-result'):unknown?primary('查询原任务','query-task'):failed?secondary('查看金币明细','wallet'):secondary('返回作品，稍后查看','works')}${unknown||failed?'<button class="text-button" data-action="works">返回作品</button>':''}</div>`});
  }
  function worksPage() {
    if(!user())return screen(empty('让灵感有迹可循','登录后，查看你正在生成和已完成的作品。','works','登录查看作品','login-works'),{active:'works'});
    const list=state.scenario==='empty'?[]:user().tasks.filter(t=>state.filter==='all'||(state.filter==='done'?t.status==='succeeded':!['succeeded','failed','canceled','expired'].includes(t.status)));
    return screen(`<div class="screen-heading"><h2>我的作品</h2><button class="icon-button" data-action="refresh-works" aria-label="刷新作品">${icon('refresh')}</button></div><div class="segmented" aria-label="作品筛选">${[['all','全部'],['active','进行中'],['done','已完成']].map(([value,title])=>`<button data-action="filter" data-id="${value}" class="${state.filter===value?'selected':''}" aria-pressed="${state.filter===value}">${title}</button>`).join('')}</div>${list.length?list.map(t=>{const e=effects.find(e=>e.id===t.effectId)||effects[0];const status=taskStatus(t);const cls=status==='succeeded'?'':status==='expired'?'expired':status==='failed'?'failed':status==='submission_unknown'?'unknown':'running';return `<button class="work-card" data-action="open-task" data-id="${t.id}" aria-label="${e.title}，${statusLabels[status]}"><div class="work-art">${art(e)}</div><div class="work-info"><h3>${e.title}</h3><p>${t.duration} 秒 · ${t.id.startsWith('demo-')?'历史演示作品':'刚刚创建'}</p><span class="status-chip ${cls}">${icon(status==='succeeded'?'check':status==='failed'?'info':'clock')} ${statusLabels[status]}</span></div><span class="work-chevron">${icon('right')}</span></button>`;}).join(''):empty(state.filter==='active'?'暂无进行中的任务':'还没有作品',state.filter==='active'?'完成后的作品会留在「全部」和「已完成」里。':'选一个喜欢的效果，开启第一段动态影像。')}<p class="app-note">${icon('clock')}<span>媒体有保存期限，请及时下载。具体有效期以作品详情为准。</span></p>`,{active:'works'});
  }
  function resultPage() {
    const t=task();if(!t)return screen(empty('找不到这件作品','它可能已被删除，请返回作品列表。','works','返回作品','works'),{title:'作品详情'});
    const status=taskStatus(t),e=effects.find(e=>e.id===t.effectId)||effects[0];const expired=status==='expired';
    if(!['succeeded','expired'].includes(status))return taskPage();
    return screen(`${expired?empty('这件作品已过期','媒体保存期限已结束，暂时无法播放、保存或分享。历史记录仍可查看。','clock','返回作品','works'):`<video class="result-player" src="assets/demo-motion.mp4" controls playsinline preload="metadata" aria-label="Vireal 本地演示片段"></video>`}<h1 class="detail-title">${e.title}</h1><p class="body-copy">${t.duration} 秒 · ${t.cost} 金币 · ${expired?'已过期':'已完成'}</p>${expired?'':`<div class="result-actions">${primary(`${icon('download')} 保存演示片段`,'save-video')}${secondary(`${icon('share')} 分享`,'share-video')}</div>`}<div class="info-card"><h3>${expired?'媒体已不可访问':'请及时保存你的作品'}</h3><p>${expired?'生成记录保留用于核对，删除记录不会返还本次金币。':'演示有效期：完成后 24 小时。真实有效期以服务器返回值为准，下载的演示文件不受页面刷新影响。'}</p></div><p class="app-note">${icon('info')}<span>播放器使用本地品牌动画，不是真实 AI 生成结果。</span></p><button class="text-button danger" data-action="delete-task">${icon('trash')} 删除作品记录</button>`,{title:'作品详情'});
  }
  function menuRow(label,symbol,action,end='',extra='') { return `<button class="menu-row" data-action="${action}" ${extra}>${icon(symbol)}<span>${label}</span><span class="row-end">${end}${icon('right')}</span></button>`; }
  function accountPage() {
    const u=user();return screen(`<div class="screen-heading"><h2>我的</h2>${u?`<button class="icon-button" data-action="settings" aria-label="账户设置">${icon('settings')}</button>`:''}</div><div class="profile-hero"><div class="avatar">${u?'V':'✦'}</div><div><h3>${u?esc(u.nickname):'每一面，都属于你'}</h3><p>${u?esc(u.email):'登录，留住每一次灵感'}</p></div></div>${u?`<button class="wallet-teaser" data-action="wallet"><div class="top"><span>我的金币</span>${icon('right')}</div><div class="balance">${balance()} <span class="coin">✦</span></div><div class="bottom">查看金币明细 · 充值暂未开放</div></button>`:primary('登录 Vireal','login-account')}<div class="section-title"><h3>帮助与设置</h3></div><div class="menu-list">${menuRow('使用说明','help','legal','','data-kind="guide"')}${menuRow('隐私说明','shield','legal','','data-kind="privacy"')}${menuRow('服务说明','info','legal','','data-kind="terms"')}${u?menuRow('账户设置','settings','settings'):''}</div><div class="account-footer">VIREAL · BECOME YOUR NEXT<br>iPhone 内测设计 · 演示数据</div>`,{active:'account'});
  }
  function walletPage() {
    if(!user())return loginPage();const ledger=state.scenario==='empty'?[]:user().ledger;
    return screen(`<div class="wallet-balance"><p>当前金币</p><strong>${balance()} <span style="font-size:30px">✦</span></strong><small>仅用于本地原型体验</small></div>${notice('内测版暂未开放充值。此处不会发起真实付款。')}${secondary('充值暂未开放','recharge','disabled')}<div class="section-title"><h3>金币明细</h3><span>最近变动</span></div>${ledger.length?ledger.map(l=>`<div class="ledger-row"><div><strong>${esc(l.reason)}</strong><p>${esc(l.date)}</p></div><b class="${l.delta>0?'positive':''}">${l.delta>0?'+':''}${l.delta}</b></div>`).join(''):empty('暂无金币变动','生成扣币与失败退回会记录在这里。','wallet','','')}<p class="app-note">${icon('info')}<span>真实余额与退币由服务器管理，客户端只展示结果。</span></p>`,{title:'我的金币'});
  }
  function settingsPage() {
    if(!user())return loginPage();
    return screen(`<div class="section-title"><h3>账户资料</h3></div><div class="menu-list">${menuRow('昵称','person','edit-nickname',esc(user().nickname))}<div class="menu-row">${icon('shield')}<span>登录邮箱</span><span class="row-end">已验证</span></div></div><p class="upload-tip">${esc(user().email)}</p><div class="section-title"><h3>登录与设备</h3></div><div class="info-card"><h3>当前 App 会话</h3><p>退出当前 App 不会退出网页或其他设备。你的作品与金币保留在账户中。</p></div>${secondary(`${icon('logout')} 退出登录`,'logout')}<div class="section-title"><h3>原型体验</h3></div>${secondary('体验另一个演示账户','switch-account')}<p class="upload-tip">切换到一个没有作品的演示账户，可检查数据隔离。刷新页面会重置所有演示数据。</p>`,{title:'账户设置'});
  }
  function legalPage() {
    const title={guide:'使用说明',privacy:'隐私说明',terms:'服务说明'}[state.legalKind];
    const content={
      guide:'<h3>从照片到动态影像</h3><p>在发现页选择效果，按提示添加一张或两张照片，再选择时长并确认费用。提交后可在作品中查看任务状态。</p><h3>任务状态与金币</h3><p>提交结果不明时请查询原任务，不要重复生成。失败是否退币，以金币明细和服务端任务记录为准。</p><h3>及时保存作品</h3><p>作品详情会显示媒体有效期。到期后可能无法播放或下载，请提前保存。</p>',
      privacy:'<h3>原型如何处理照片</h3><p>你选中的照片仅通过本机浏览器预览，不会上传。退出演示账户、重置演示或刷新页面后，临时照片引用会清除。</p><h3>演示账户</h3><p>邮箱、验证码、金币和任务只用于本机交互模拟，不连接 Clerk 或业务服务器。请勿输入真实密码或其他敏感资料。</p><h3>真实客户端上线前</h3><p>需要明确照片的处理用途、模型服务提供方、媒体保留期限、删除方式及联系渠道，再提供正式隐私政策。</p>',
      terms:'<h3>照片使用</h3><p>请确认你有权使用照片，并已获得照片中人物的同意。不得使用他人照片制作侵权或有害内容。</p><h3>内测范围</h3><p>首版以内测登录、上传、生成和作品管理为目标，充值暂未开放。服务和地区可用性由服务器决定。</p><h3>演示与真实服务</h3><p>原型不产生真实订单、扣币或模型调用。演示价格、余额、保留期限和处理时间不构成真实服务承诺。</p>',
    }[state.legalKind];
    return screen(`<div class="legal-copy">${notice('设计预览说明，不替代正式上线条款。')}${content}</div>`,{title});
  }
  function render() {
    const scroll = renderedScreen === state.screen ? ($('.screen-content')?.scrollTop || 0) : 0;
    const notes=pages[state.screen];
    $('#screen-nav').innerHTML=Object.entries(pages).filter(([key])=>key!=='legal').map(([key,page])=>`<button data-screen="${key}" class="${state.screen===key?'active':''}" ${state.screen===key?'aria-current="page"':''}>${icon(page.symbol)}${page.title}</button>`).join('');
    $('#screen-notes').innerHTML=`<h2>${notes.title}</h2><p class="description">${notes.description}</p><div class="note-label">交互要点</div><ul class="note-list">${notes.points.map(p=>`<li>${p}</li>`).join('')}</ul><div class="note-label">复用现有接口</div>${notes.apis.map(([method,path])=>`<div class="endpoint"><b>${method}</b>/api/v1/app${path}</div>`).join('')}`;
    $('#scenario').value=state.scenario;$('#scenario-help').textContent=scenarioHelp[state.scenario];
    const renderers={home:homePage,detail:detailPage,login:loginPage,create:createPage,task:taskPage,works:worksPage,result:resultPage,account:accountPage,wallet:walletPage,settings:settingsPage,legal:legalPage};
    if(state.scenario==='offline')$('#app').innerHTML=screen(empty('网络暂时断开','请检查网络连接。恢复后可以继续刚才的操作。','network','重新连接','recover'),{title:'连接状态'});
    else if(state.scenario==='loading')$('#app').innerHTML=screen('<div role="status" aria-label="正在加载"><div class="skeleton title"></div><div class="skeleton block"></div><div class="skeleton line"></div><div class="skeleton line short"></div></div><button class="secondary" data-action="recover" style="margin-top:30px">完成加载</button>',{title:notes.title});
    else $('#app').innerHTML=renderers[state.screen]();
    renderedScreen=state.screen;
    if($('.screen-content'))$('.screen-content').scrollTop=scroll;
  }
  function modal(title,body,confirm='知道了',action=null,{cancel=false}={}) {
    modalAction=action;
    $('#modal').innerHTML=`<h2 id="modal-title">${title}</h2>${body}<button class="primary" data-action="modal-confirm">${confirm}</button>${cancel?secondary('取消','modal-cancel'):''}`;
    if(!$('#modal').open)$('#modal').showModal();
  }
  function closeModal(){ $('#modal').close();$('#modal').querySelectorAll('video').forEach(v=>v.pause());modalAction=null; }
  function blockedSubmission(){return !user()||Boolean(unavailable())||state.scenario==='offline'||balance()<currentVariant().cost;}
  function createTask() {
    if(state.submission){state.selectedTask=state.submission;closeModal();go('task');return;}
    const e=currentEffect(),v=currentVariant();
    if(blockedSubmission()||!state.authorized||!Array.from({length:e.count},(_,i)=>state.uploads[i]).every(Boolean)){closeModal();toast('请先确认照片、授权和可用状态');return;}
    const id=uid();const now=Date.now();
    const next={id,effectId:e.id,variantId:v.id,status:'pending',createdAt:now,cost:v.cost,duration:v.duration,idempotencyKey:uid(),ownerId:user().id};
    user().tasks.unshift(next);user().balance-=v.cost;user().ledger.unshift({reason:`${e.title} · ${v.duration} 秒`,delta:-v.cost,date:'刚刚 · 演示'});
    state.submission=id;state.selectedTask=id;closeModal();go('task');toast('演示任务已提交，可在作品中查看');
  }
  function stageTasks() {
    if(document.hidden||!user()||state.scenario!=='normal')return;
    let changed=false;
    for(const t of user().tasks){if(!t.idempotencyKey||['succeeded','failed','expired','canceled'].includes(t.status))continue;
      const age=Date.now()-t.createdAt;const next=age<2000?'pending':age<9000?'running':age<12000?'saving':'succeeded';
      if(next!==t.status){t.status=next;changed=true;}
    }
    if(changed&&['task','works'].includes(state.screen)){
      const scroll=$('.screen-content')?.scrollTop||0;render();$('.screen-content').scrollTop=scroll;
    }
  }
  function clearIdentity(){clearUploads();state.userKey=null;state.selectedTask=null;state.history=[];state.filter='all';state.returnScreen='create';}
  function reset(){closeModal();clearUploads();state.users.clear();Object.assign(state,{screen:'home',history:[],category:'all',effectId:'dance-1',variantId:'dance-5',scenario:'normal',userKey:null,selectedTask:null,filter:'all',loginStage:'email',loginEmail:defaultEmail,loginError:'',returnScreen:'create'});go('home',{replace:true});toast('演示已重置');}
  function setScenario(value){
    state.scenario=value;
    if(value==='authExpired'){const returnTo=state.screen;clearIdentity();state.returnScreen=['create','works','wallet','account'].includes(returnTo)?returnTo:'works';state.loginStage='email';go('login');toast('登录已失效，请重新登录');return;}
    if(['lowbalance','quota'].includes(value)){ensureDemoUser();go('create');return;}
    if(['closed','removed'].includes(value)){go('detail');return;}
    if(['unknown','failed','expired'].includes(value)){ensureDemoUser();state.selectedTask=user().tasks[0]?.id;if(!state.selectedTask){state.userKey=seedUser(defaultEmail);state.selectedTask=user().tasks[0]?.id;}go(value==='expired'?'result':'task');return;}
    render();
  }
  document.addEventListener('click',(event)=>{
    const screenButton=event.target.closest('[data-screen]');
    if(screenButton){const key=screenButton.dataset.screen;if(['create','task','works','result','account','wallet','settings'].includes(key))ensureDemoUser();if(['task','result'].includes(key)&&!task())state.userKey=seedUser(defaultEmail);if(['task','result'].includes(key)&&!state.selectedTask)state.selectedTask=user().tasks[0]?.id;go(key);return;}
    if(event.target.closest('#reset-demo')){reset();return;}
    const target=event.target.closest('[data-action]');if(!target||target.disabled)return;
    const action=target.dataset.action;
    switch(action){
      case 'back':back();break;
      case 'home':go('home');break;
      case 'tab':go(target.dataset.route);break;
      case 'category':state.category=target.dataset.id;render();break;
      case 'all-category':state.category='all';render();break;
      case 'effect':chooseEffect(target.dataset.effect);go('detail');break;
      case 'use-effect':if(!unavailable())needLogin('create');break;
      case 'new-creation':{const previous=user()?.tasks.find(t=>t.id===state.submission)||task();if(previous){state.effectId=previous.effectId;state.variantId=previous.variantId;}clearUploads();go('create');break;}
      case 'wallet':needLogin('wallet');break;
      case 'works':go('works');break;
      case 'settings':needLogin('settings');break;
      case 'login-works':needLogin('works');break;
      case 'login-account':needLogin('account');break;
      case 'change-email':state.loginStage='email';state.loginError='';render();$('#login-input').focus();break;
      case 'legal':state.legalKind=target.dataset.kind||'guide';go('legal');break;
      case 'recover':state.scenario='normal';render();break;
      case 'variant':state.variantId=target.dataset.id;state.submission=null;render();break;
      case 'choose-photo':$(`input[data-photo="${target.dataset.index}"]`).click();break;
      case 'remove-photo':{const i=Number(target.dataset.index);photoRequests.delete(i);if(state.uploads[i]?.url?.startsWith('blob:'))URL.revokeObjectURL(state.uploads[i].url);state.uploads[i]=null;state.submission=null;render();break;}
      case 'demo-photo':{
        clearUploads();state.uploads=Array.from({length:currentEffect().count},()=>({url:'assets/demo-photo.svg',name:'演示占位图'}));render();toast('已添加演示占位图，可继续体验');break;
      }
      case 'confirm-generate':{
        if(state.submission){state.selectedTask=state.submission;go('task');break;}
        modal('确认生成视频',`<p>${esc(currentEffect().title)} · ${currentVariant().duration} 秒<br>本次演示消耗 <strong>${currentVariant().cost} 金币</strong>，剩余 ${balance()-currentVariant().cost} 金币。</p><p>仅模拟创作过程，不上传照片、不调用模型，也不扣真实金币。</p>`,'确认演示生成',createTask,{cancel:true});break;
      }
      case 'modal-confirm':{const run=modalAction;closeModal();if(run)run();break;}
      case 'modal-cancel':closeModal();break;
      case 'preview-video':modal('品牌动画演示','<video src="assets/demo-motion.mp4" controls playsinline preload="metadata" aria-label="本地品牌演示片段"></video><p>此片段用于体验播放操作，不代表当前效果的真实生成结果。</p>');break;
      case 'query-task':toast('已查询原演示任务，结果仍待确认；未重新生成');break;
      case 'view-result':go('result');break;
      case 'filter':state.filter=target.dataset.id;render();break;
      case 'open-task':state.selectedTask=target.dataset.id;go(['succeeded','expired'].includes(taskStatus(task()))?'result':'task');break;
      case 'refresh-works':stageTasks();toast('作品状态已刷新');break;
      case 'save-video':{if(taskStatus(task())!=='succeeded')return;const a=document.createElement('a');a.href='assets/demo-motion.mp4';a.download='vireal-demo.mp4';document.body.append(a);a.click();a.remove();toast('正在保存本地演示片段');break;}
      case 'share-video':{
        modal('分享作品',`<p>原生 App 将在这里打开 iPhone 系统分享面板，分享服务端下载的作品文件。</p><p>本原型可保存本地演示片段后手动分享。</p>`,'保存演示片段',()=>{const a=document.createElement('a');a.href='assets/demo-motion.mp4';a.download='vireal-demo.mp4';a.click();});break;
      }
      case 'delete-task':{const id=task()?.id;modal('删除这件作品？','<p>此操作会移除当前账户中的演示记录，金币不会返还。真实服务会同时处理可删除的输出媒体。</p>','删除记录',()=>{if(!user())return;user().tasks=user().tasks.filter(t=>t.id!==id);if(state.submission===id)state.submission=null;state.selectedTask=null;state.history=[];go('works',{replace:true});toast('演示作品已删除');},{cancel:true});break;}
      case 'edit-nickname':modal('修改昵称',`<div class="form-group"><label for="nickname">昵称</label><input id="nickname" maxlength="50" value="${esc(user().nickname)}"></div><div id="nickname-error" class="form-error" role="alert"></div>`,'保存',()=>{const name=$('#nickname')?.value.trim();if(name&&user()){user().nickname=name;render();toast('昵称已更新');}});break;
      case 'logout':modal('退出当前账户？','<p>退出后将清除本机临时照片和账户页面。账户中的演示作品会保留，重新登录可继续查看。</p>','退出登录',()=>{clearIdentity();state.scenario='normal';go('account',{replace:true});toast('已退出当前演示会话');},{cancel:true});break;
      case 'switch-account':clearIdentity();state.userKey=seedUser('another@vireal.example');state.scenario='normal';go('account',{replace:true});toast('已切换至另一个演示账户');break;
    }
  });
  // Keep validation inside the dialog so an invalid value cannot silently close it.
  $('#modal').addEventListener('click',(event)=>{
    if(!event.target.closest('[data-action="modal-confirm"]')||!$('#nickname'))return;
    if(!$('#nickname').value.trim()){$('#nickname-error').textContent='昵称不能为空';$('#nickname').focus();event.stopPropagation();}
  });
  document.addEventListener('submit',(event)=>{
    if(event.target.dataset.form!=='login')return;event.preventDefault();
    const values=new FormData(event.target);
    if(state.loginStage==='email'){state.loginEmail=String(values.get('email')).trim().toLowerCase();state.loginStage='code';state.loginError='';render();$('#login-input').focus();return;}
    if(values.get('code')!=='123456'){state.loginError='演示验证码不正确，请输入 123456。';$('#login-error').textContent=state.loginError;return;}
    state.userKey=seedUser(state.loginEmail);state.loginError='';state.scenario=state.scenario==='authExpired'?'normal':state.scenario;state.history=[];go(state.returnScreen,{replace:true});toast('演示登录成功，已返回刚才的页面');
  });
  document.addEventListener('change',(event)=>{
    if(event.target.id==='scenario'){setScenario(event.target.value);return;}
    if(event.target.id==='photo-consent'){state.authorized=event.target.checked;const scroll=$('.screen-content').scrollTop;render();$('.screen-content').scrollTop=scroll;return;}
    if(!event.target.matches('[data-photo]'))return;
    const file=event.target.files[0],index=Number(event.target.dataset.photo);if(!file)return;
    if(file.size>15*1024*1024){toast('原型仅预览 15 MB 以内的图片');event.target.value='';return;}
    if(!/^image\/(jpeg|png|webp|heic|heif)$/.test(file.type)){toast('请选择 JPG、PNG、WebP 或可预览的 HEIC 图片');event.target.value='';return;}
    const owner=user()?.id,epoch=photoEpoch,requestId=uid(),url=URL.createObjectURL(file),image=new Image();
    photoRequests.set(index,requestId);
    image.onload=()=>{if(owner!==user()?.id||epoch!==photoEpoch||photoRequests.get(index)!==requestId||state.screen!=='create'){URL.revokeObjectURL(url);return;}if(state.uploads[index]?.url?.startsWith('blob:'))URL.revokeObjectURL(state.uploads[index].url);state.uploads[index]={url,name:file.name};state.submission=null;render();};
    image.onerror=()=>{URL.revokeObjectURL(url);toast('此图片暂不能预览，请转为 JPG 或 PNG');};image.src=url;
  });
  $('#modal').addEventListener('close',()=>{$('#modal').querySelectorAll('video').forEach(v=>v.pause());});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)stageTasks();});
  window.addEventListener('pagehide',()=>{clearUploads();clearInterval(taskInterval);clearTimeout(toastTimer);});
  window.addEventListener('hashchange',()=>{const key=location.hash.slice(1);if(!pages[key])return;if(['create','task','result','wallet','settings'].includes(key)&&!user()){state.returnScreen=key;go('login');}else go(key);});
  const initial=location.hash.slice(1);if(pages[initial]){if(['create','task','result','wallet','settings'].includes(initial))state.returnScreen=initial;state.screen=['create','task','result','wallet','settings'].includes(initial)?'login':initial;}
  const taskInterval=setInterval(stageTasks,750);
  render();
})();
