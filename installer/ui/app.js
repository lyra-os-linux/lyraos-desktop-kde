const pages=[...document.querySelectorAll('[data-page]')];
const steps=[...document.querySelectorAll('.step')];
const back=document.querySelector('#back');
const next=document.querySelector('#next');
const progress=document.querySelector('#progress-bar');
const actionProgress=document.querySelector('.action-progress');
const label=document.querySelector('#step-label');
const finalActions=document.querySelector('#final-actions');
const install=document.querySelector('#install');
const installConfirm=document.querySelector('#install-confirm');
const installConfirmControl=document.querySelector('#install-confirm-control');
const installStatus=document.querySelector('#install-status');
const installStatusTitle=document.querySelector('#install-status-title');
const reboot=document.querySelector('#reboot');
const rebootError=document.querySelector('#reboot-error');
const {invoke}=window.__TAURI__.core;
const {listen}=window.__TAURI__.event;
const i18n=window.LyraI18n;
const DEFAULT_LOCALE='en_US.UTF-8';
let selectedLocale=DEFAULT_LOCALE;
let current=0;
let storageSnapshot=null;
let selectedDiskPath=null;
let swapChoice='Zram';
let selectedPlan=null;
let summaryConfigValid=false;
let installing=false;
let installationTerminal=false;
let knownScreenSize=`${screen.availWidth}x${screen.availHeight}`;

async function fitWindowToMonitor(){
  try{
    await invoke('fit_window_to_monitor');
  }catch(error){
    console.error('Não foi possível ajustar a janela à área útil do monitor',error);
  }
}

const keyboardLayouts=[
  ['br-abnt2','Português (Brasil)','ABNT2 · Português brasileiro','Português','Q W E R T Y Ç ⌫'],
  ['br','Português (Brasil)','Português · variante internacional','Português','Q W E R T Y ´ ⌫'],
  ['pt','Português (Portugal)','Português europeu','Português','Q W E R T Y Ç ⌫'],
  ['us','English (US)','US · padrão ANSI','English','Q W E R T Y [ ⌫'],
  ['us-intl','English (US)','US International · dead keys','English','Q W E R T Y ´ ⌫'],
  ['gb','English (UK)','United Kingdom · ISO','English','Q W E R T Y # ⌫'],
  ['ca','English (Canada)','Canadian Multilingual','English','Q W E R T Y À ⌫'],
  ['ie','English (Ireland)','Irish','English','Q W E R T Y € ⌫'],
  ['es','Español','Espanha · ISO','Europa','Q W E R T Y Ñ ⌫'],
  ['latam','Español (Latinoamérica)','Latin American','América Latina','Q W E R T Y Ñ ⌫'],
  ['fr','Français','AZERTY · França','Europa','A Z E R T Y M ⌫'],
  ['be','Français (Bélgica)','AZERTY · Bélgica','Europa','A Z E R T Y µ ⌫'],
  ['de','Deutsch','QWERTZ · Alemanha','Europa','Q W E R T Z Ü ⌫'],
  ['ch-de','Deutsch (Suíça)','QWERTZ · Suíça','Europa','Q W E R T Z Ä ⌫'],
  ['it','Italiano','Itália · ISO','Europa','Q W E R T Y ò ⌫'],
  ['nl','Nederlands','Holanda · ISO','Europa','Q W E R T Y ë ⌫'],
  ['se','Svenska','Suécia · ISO','Nórdicos','Q W E R T Y Å ⌫'],
  ['no','Norsk','Noruega · ISO','Nórdicos','Q W E R T Y Ø ⌫'],
  ['dk','Dansk','Dinamarca · ISO','Nórdicos','Q W E R T Y Æ ⌫'],
  ['fi','Suomi','Finlândia · ISO','Nórdicos','Q W E R T Y Å ⌫'],
  ['is','Íslenska','Islândia · ISO','Nórdicos','Q W E R T Y Ð ⌫'],
  ['pl','Polski','Polônia · programadores','Europa','Q W E R T Y Ł ⌫'],
  ['cz','Čeština','Tcheco · QWERTZ','Europa','Q W E R T Z Ě ⌫'],
  ['sk','Slovenčina','Eslovaco · QWERTZ','Europa','Q W E R T Z Ľ ⌫'],
  ['hu','Magyar','Húngaro · QWERTZ','Europa','Q W E R T Z Ő ⌫'],
  ['ro','Română','Romênia · standard','Europa','Q W E R T Y Ă ⌫'],
  ['tr','Türkçe','Turquia · QWERTY','Europa','Q W E R T Y Ş ⌫'],
  ['ru','Русский','Russo · ЙЦУКЕН','Cirílico','Й Ц У К Е Н Г Ш ⌫'],
  ['ua','Українська','Ucraniano · ЙЦУКЕН','Cirílico','Й Ц У К Е Н І Ї ⌫'],
  ['bg','Български','Búlgaro · fonético','Cirílico','Я В Е Р Т Ъ У И ⌫'],
  ['el','Ελληνικά','Grego · QWERTY','Cirílico','; ς Ε Ρ Τ Υ Θ ⌫'],
  ['he','עברית','Hebraico · IL','Oriente Médio','/ ק ר א ט י ו ⌫'],
  ['ar','العربية','Árabe · 101','Oriente Médio','ض ص ث ق ف غ ع ه ⌫'],
  ['fa','فارسی','Persa · ISIRI 2901','Oriente Médio','ض ص ث ق ف ع ه خ ⌫'],
  ['ja','日本語','Japonês · JIS','Ásia','Q W E R T Y む ほ ⌫'],
  ['ko','한국어','Coreano · 2-set','Ásia','ㅂ ㅈ ㄷ ㄱ ㅅ ㅛ ㅕ ㅑ ⌫'],
  ['zh-pinyin','中文','Chinês · Pinyin','Ásia','Q W E R T Y U I ⌫'],
  ['th','ไทย','Tailandês · Kedmanee','Ásia','ฟ ห ก ด เ ้ ร า ⌫'],
  ['in','English (India)','Inglês · Índia','Ásia','Q W E R T Y U I ⌫'],
  ['pk','اردو','Urdu · Pakistan','Ásia','ط ظ ذ د ڈ ر ڑ ⌫'],
  ['la','Latina','Latim · clássico','Especial','Q W E R T Y Æ Œ ⌫'],
  ['dvorak','English (US)','Dvorak · ergonômico','Alternativos','\' , . P Y F G C R L ⌫'],
  ['colemak','English (US)','Colemak · ergonômico','Alternativos','Q W F P G J L U Y ; ⌫'],
];

const languages=[
  ['en_US.UTF-8','English (United States)','🇺🇸','en_US'],
  ['pt_BR.UTF-8','Português (Brasil)','🇧🇷','pt_BR'],
  ['es_ES.UTF-8','Español (España)','🇪🇸','es_ES'],
];

function uiLocale(locale){return {
  'pt_BR.UTF-8':'pt-BR',
  'es_ES.UTF-8':'es-ES',
}[locale]||'en-US'}

async function loadInstallerLogo(){
  const image=document.querySelector('#brand-logo');
  try{
    const bytes=await invoke('installer_logo');
    let binary='';
    for(let offset=0;offset<bytes.length;offset+=8192){
      binary+=String.fromCharCode(...bytes.slice(offset,offset+8192));
    }
    image.src=`data:image/png;base64,${btoa(binary)}`;
  }catch(error){
    image.alt='Lyra Installer';
    console.error('Não foi possível carregar o logo do instalador',error);
  }
}

function renderLanguageCards(query=''){
  const normalized=query.trim().toLocaleLowerCase();
  const matches=languages.filter(([,name,,code])=>`${name} ${code}`.toLocaleLowerCase().includes(normalized));
  document.querySelector('#language-cards').innerHTML=matches.map(([value,name,flag,code])=>`<label class="choice${value===selectedLocale?' selected':''}"><input type="radio" name="locale" value="${value}" ${value===selectedLocale?'checked':''}/><span><strong><span class="language-flag" aria-hidden="true">${flag}</span>${name}</strong><small>${code}</small></span><b>✓</b></label>`).join('')||`<p class="keyboard-empty">${i18n.t('noLanguages')}</p>`;
  document.querySelector('#language-count').textContent=i18n.t('languageCount',{count:matches.length});
}

function renderKeyboardCards(query=''){
  const normalized=query.trim().toLocaleLowerCase();
  const matches=keyboardLayouts.filter(([,name,variant,group])=>`${name} ${variant} ${group}`.toLocaleLowerCase().includes(normalized));
  const groupKeys={'Português':'language','English':'language','Europa':'europe','América Latina':'latinAmerica','Nórdicos':'nordic','Cirílico':'cyrillic','Oriente Médio':'middleEast','Ásia':'asia','Especial':'special','Alternativos':'alternative'};
  const cards=matches.map(([id,name,,group,keys])=>`<label class="keyboard-card${id==='br-abnt2'?' selected':''}"><input type="radio" name="keyboard" value="${id}" ${id==='br-abnt2'?'checked':''}/><span class="keyboard-top"><strong>${name}</strong><b>✓</b></span><small>${id} · ${i18n.t(`keyboardGroup.${groupKeys[group]||'language'}`)}</small><div class="keyboard-layout">${keys.split(' ').map(key=>`<i>${key}</i>`).join('')}</div></label>`).join('');
  document.querySelector('#keyboard-cards').innerHTML=cards||`<p class="keyboard-empty">${i18n.t('noKeyboards')}</p>`;
  document.querySelector('#keyboard-count').textContent=i18n.t('keyboardCount',{count:matches.length});
}

const transportLabel=transport=>({Nvme:'NVMe',Sata:'SATA',Virtio:'VirtIO',Usb:'USB'}[transport]||i18n.t('unknownTransport'));

function diskTitle(disk){
  const meaningfulLabel=value=>value&&!/^0x[0-9a-f]+$/i.test(value.trim());
  if(meaningfulLabel(disk.model)) return disk.model.trim();
  if(meaningfulLabel(disk.vendor)) return disk.vendor.trim();

  // VirtIO disks commonly expose only their PCI vendor ID (for example
  // 0x1af4) through lsblk. That identifier is useful to the kernel, not to
  // someone choosing an installation target.
  const transport=disk.transport==='Unknown'&&disk.kname.startsWith('vd')?'Virtio':disk.transport;
  return transport!=='Unknown'
    ?i18n.t('diskNamed',{transport:transportLabel(transport)})
    :i18n.t('diskGeneric',{name:disk.kname});
}

function formatBytes(bytes){
  const units=['B','KiB','MiB','GiB','TiB'];
  let value=bytes,i=0;
  while(value>=1024&&i<units.length-1){value/=1024;i++;}
  return `${value.toFixed(i>0&&value<10?1:0)} ${units[i]}`;
}

function diskIneligibleReason(disk){
  if(disk.is_live_media) return i18n.t('diskLiveMedia');
  if(disk.role==='RaidMember') return i18n.t('diskRaidMember');
  if(disk.role==='LvmPhysicalVolume') return i18n.t('diskLvmMember');
  return null;
}

function diskStatus(disk){
  const reason=diskIneligibleReason(disk);
  if(reason) return reason;
  if(disk.role==='Unsupported') return i18n.t('diskWillErase');
  return i18n.t('diskAvailable');
}

function localizedErasedItems(){
  const disk=(storageSnapshot?.disks||[]).find(candidate=>candidate.path===selectedDiskPath);
  return (disk?.partitions||[]).map(partition=>i18n.t('erasedPartition',{
    path:partition.path,
    filesystem:partition.filesystem||i18n.t('unknownFilesystem'),
    mount:partition.mountpoints?.length?i18n.t('mountedAt',{path:partition.mountpoints[0]}):'',
    size:formatBytes(partition.size_bytes),
  }));
}

function renderDiskCards(){
  const list=document.querySelector('#disk-list');
  const disks=storageSnapshot?.disks||[];
  if(!disks.length){
    list.innerHTML=`<p class="keyboard-empty">${i18n.t('noDisks')}</p>`;
    document.querySelector('#disk-count').textContent='';
    return;
  }
  list.innerHTML=disks.map(disk=>{
      const reason=diskIneligibleReason(disk);
      const title=diskTitle(disk);
      const selected=disk.path===selectedDiskPath;
      return `<label class="disk-card${selected?' selected':''}${reason?' disk-card-disabled':''}">
        <input type="radio" name="disk" value="${disk.path}" ${selected?'checked':''} ${reason?'disabled':''}/>
        <span class="disk-top"><strong>${title}</strong><b>✓</b></span>
        <small>${disk.path} · ${formatBytes(disk.size_bytes)} · ${transportLabel(disk.transport)}</small>
        <span class="disk-status${reason?' disk-status-blocked':''}">${diskStatus(disk)}</span>
      </label>`;
  }).join('');
  document.querySelector('#disk-count').textContent=i18n.t('diskCount',{count:disks.length,s:disks.length===1?'':'s'});
}

async function discoverStorage(){
  try{
    storageSnapshot=await invoke('discover_storage');
  }catch(error){
    storageSnapshot=null;
    console.error('Could not discover storage',error);
    document.querySelector('#disk-list').innerHTML=`<p class="disk-plan-error">${i18n.t('storageDiscoveryFailed')}</p>`;
    document.querySelector('#disk-count').textContent='';
    return;
  }
  renderDiskCards();
}

function renderPlan(plan){
  const box=document.querySelector('#disk-plan');
  const esp=plan.esp.Reuse
    ?i18n.t('espReuse',{path:plan.esp.Reuse.path})
    :i18n.t('espCreate',{size:formatBytes(plan.esp.Create.size_bytes)});
  const erased=localizedErasedItems();
  const swap=plan.swap==='None'
    ?i18n.t('swapNone')
    :(plan.swap==='Zram'?i18n.t('swapZram'):i18n.t('swapDisk',{size:formatBytes(plan.swap.Partition.size_bytes)}));
  box.hidden=false;
  box.innerHTML=`
    <div class="plan-row"><span>${i18n.t('planEfi')}</span><strong>${esp}</strong></div>
    <div class="plan-row"><span>${i18n.t('planFilesystem')}</span><strong>${i18n.t('planBtrfs',{count:plan.root_filesystem.Btrfs.subvolumes.length})}</strong></div>
    <div class="plan-row"><span>${i18n.t('planMemory')}</span><strong>${swap}</strong></div>
    ${erased.length?`<div class="plan-warning"><strong>${i18n.t('planErased')}</strong><ul>${erased.map(item=>`<li>${item}</li>`).join('')}</ul></div>`:''}
  `;
}

function buildGuidedChoice(){
  if(!selectedDiskPath) return null;
  return {raw_target:{Disk:selectedDiskPath},volume_layer:'Direct',swap:swapChoice};
}

async function refreshPlan(){
  const box=document.querySelector('#disk-plan');
  selectedPlan=null;
  const choice=buildGuidedChoice();
  if(!choice){
    box.hidden=true;
    updateNextButtonState();
    return;
  }
  box.hidden=false;
  box.innerHTML=`<p class="keyboard-empty">${i18n.t('calculatingPlan')}</p>`;
  try{
    selectedPlan=await invoke('plan_install',{snapshot:storageSnapshot,choice});
    renderPlan(selectedPlan);
  }catch(error){
    selectedPlan=null;
    console.error('Could not plan installation',error);
    box.innerHTML=`<p class="disk-plan-error">${i18n.t('planFailed')}</p>`;
  }
  updateNextButtonState();
}

function updateNextButtonState(){
  const gated=(current===5&&!selectedPlan)||installing||installationTerminal;
  next.disabled=gated;
  next.style.opacity=gated?'.45':'1';
}

function updateInstallButtonState(){
  const enabled=current===6&&selectedPlan&&summaryConfigValid&&installConfirm.checked&&!installing&&!installationTerminal;
  install.disabled=!enabled;
  installConfirm.disabled=installing||installationTerminal||!summaryConfigValid;
  finalActions.hidden=current!==6;
  installConfirmControl.hidden=current!==6||installConfirm.checked||installing||installationTerminal;
  install.hidden=current!==6||!installConfirm.checked||installing||installationTerminal;
}

function show(index){
  current=index;
  pages.forEach((page,i)=>page.classList.toggle('page-active',i===index));
  steps.forEach((step,i)=>step.classList.toggle('active',i===index));
  back.disabled=index===0||installing||installationTerminal;
  back.hidden=index===6&&(installing||installationTerminal);
  next.hidden=index===6;
  actionProgress.hidden=index===6;
  next.innerHTML=i18n.t('next');
  progress.style.width=`${(index+1)*14.2857}%`;
  label.textContent=i18n.t('step',{current:`0${index+1}`});
  updateNextButtonState();
  updateInstallButtonState();
}

function validate(){
  const errors=[];
  const hostname=document.querySelector('#hostname').value;
  const username=document.querySelector('#username').value;
  const fullName=document.querySelector('#full-name').value.trim();
  const password=document.querySelector('#password').value;
  const confirm=document.querySelector('#password-confirm').value;
  const bytes=value=>new TextEncoder().encode(value).length;
  if(!fullName) errors.push('validation.fullNameRequired');
  else if(/[\0:\n]/.test(fullName)||bytes(fullName)>131071) errors.push('validation.invalidFullName');
  if(!/^[a-z][a-z0-9_-]{0,31}$/.test(username)||username==='root') errors.push('validation.invalidUsername');
  if(!/^[A-Za-z0-9][A-Za-z0-9-]{0,61}[A-Za-z0-9]$/.test(hostname)) errors.push('validation.invalidHostname');
  if([...password].length<8) errors.push('validation.passwordTooShort');
  if(/[\0\n]/.test(password)) errors.push('validation.invalidPassword');
  if(bytes(username)+bytes(password)+2>8191) errors.push('validation.passwordTooLong');
  if(password!==confirm) errors.push('validation.passwordMismatch');
  document.querySelector('#validation').textContent=errors.map(key=>i18n.t(key)).join(' · ');
  return errors.length===0;
}

function suggestedUsername(fullName){
  const normalized=fullName
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g,'')
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g,' ')
    .trim();
  const first=normalized.split(/\s+/)[0]||'';
  return /^[a-z]/.test(first)?first.slice(0,32):'';
}

function collectInstallConfig(){
  return {
    locale: document.querySelector('input[name=locale]:checked').value,
    timezone: document.querySelector('#timezone').value,
    keyboard_layout: document.querySelector('input[name=keyboard]:checked').value,
    hostname: document.querySelector('#hostname').value,
    full_name: document.querySelector('#full-name').value.trim(),
    username: document.querySelector('#username').value,
    password: document.querySelector('#password').value,
  };
}

async function updateSummary(){
  const locale=document.querySelector('input[name=locale]:checked').value;
  const language=languages.find(([value])=>value===locale);
  document.querySelector('#summary-locale').textContent=language?.[1]||locale;
  document.querySelector('#summary-hostname').textContent=document.querySelector('#hostname').value||'lyra-os';
  document.querySelector('#summary-user').textContent=document.querySelector('#username').value||i18n.t('waitingInput');
  const choice=buildGuidedChoice();
  const target=choice?.raw_target?.Disk||i18n.t('waitingSelection');
  document.querySelector('#summary-disk').textContent=target;
  document.querySelector('#summary-swap').textContent=swapChoice==='None'?i18n.t('swapNone'):swapChoice==='Disk'?i18n.t('summarySwapDisk'):'ZRAM';
  document.querySelector('#install-confirm-text').textContent=i18n.t('confirmErase',{target});
  installConfirm.checked=false;
  install.textContent=i18n.t('title');
  installStatus.hidden=true;
  installStatus.className='install-status';
  reboot.hidden=true;
  rebootError.hidden=true;

  const validationBox=document.querySelector('#summary-validation');
  summaryConfigValid=false;
  try{
    await invoke('validate_install_config',{config:collectInstallConfig()});
    validationBox.textContent='';
    summaryConfigValid=true;
  }catch(error){
    const codes=Array.isArray(error)?error:[String(error)];
    validationBox.textContent=codes.map(code=>i18n.t(code)).join(' · ');
  }
  updateInstallButtonState();
}

let timezones=[];
const robinsonX=[1,.9986,.9954,.99,.9822,.973,.96,.9427,.9216,.8962,.8679,.835,.7986,.7597,.7186,.6732,.6213,.5722,.5322];
const robinsonY=[0,.062,.124,.186,.248,.31,.372,.434,.4958,.5571,.6176,.6769,.7346,.7903,.8435,.8936,.9394,.9761,1];
const mapCentralMeridian=11.25;
const mapLatitudeCompression=.95623;
function projectTimezone(latitude,longitude){
  const absoluteLatitude=Math.min(90,Math.abs(latitude));
  const lower=Math.min(17,Math.floor(absoluteLatitude/5));
  const fraction=(absoluteLatitude-lower*5)/5;
  const xCoefficient=robinsonX[lower]+(robinsonX[lower+1]-robinsonX[lower])*fraction;
  const yCoefficient=robinsonY[lower]+(robinsonY[lower+1]-robinsonY[lower])*fraction;
  let relativeLongitude=longitude-mapCentralMeridian;
  if(relativeLongitude>180) relativeLongitude-=360;
  if(relativeLongitude< -180) relativeLongitude+=360;
  return {
    x:1377+(relativeLongitude/180)*xCoefficient*1377,
    y:699-Math.sign(latitude)*yCoefficient*699*mapLatitudeCompression,
  };
}
function selectTimezone(timezone){
  const selector=document.querySelector('#timezone');
  const entry=timezones.find(candidate=>candidate.name===timezone);
  if(!entry) return;
  selector.value=timezone;
  const {x,y}=projectTimezone(entry.latitude,entry.longitude);
  document.querySelector('#timezone-marker').setAttribute('transform',`translate(${x} ${y})`);
  document.querySelector('#timezone-marker-label').textContent=timezone;
  document.querySelector('#timezone-selection-value').textContent=timezone;
  mapCamera.x=Math.max(0,Math.min(2754-mapCamera.width,x-mapCamera.width/2));
  mapCamera.y=Math.max(0,Math.min(1398-mapCamera.height,y-mapCamera.height/2));
  renderMapCamera();
}

async function loadTimezones(){
  try{
    timezones=await invoke('list_timezones');
  }catch(error){
    timezones=[{name:'America/Sao_Paulo',latitude:-23.55,longitude:-46.63}];
    console.error(error);
  }
  const selector=document.querySelector('#timezone');
  selector.innerHTML=timezones.map(zone=>`<option value="${zone.name}">${zone.name.replaceAll('_',' ')}</option>`).join('');
  selectTimezone(timezones.some(zone=>zone.name==='America/Sao_Paulo')?'America/Sao_Paulo':timezones[0].name);
}

const mapZoomLevels=[100,125,150,200];
let mapZoomIndex=0;
const mapCamera={x:0,y:0,width:2754,height:1398,dragging:false,pointerX:0,pointerY:0};
function renderMapCamera(){
  document.querySelector('#map-canvas').setAttribute('viewBox',`${mapCamera.x} ${mapCamera.y} ${mapCamera.width} ${mapCamera.height}`);
}
function setMapZoom(index){
  const oldWidth=mapCamera.width;
  const oldHeight=mapCamera.height;
  mapZoomIndex=Math.max(0,Math.min(mapZoomLevels.length-1,index));
  const scale=mapZoomLevels[mapZoomIndex]/100;
  mapCamera.width=2754/scale;
  mapCamera.height=1398/scale;
  mapCamera.x=Math.max(0,Math.min(2754-mapCamera.width,mapCamera.x+(oldWidth-mapCamera.width)/2));
  mapCamera.y=Math.max(0,Math.min(1398-mapCamera.height,mapCamera.y+(oldHeight-mapCamera.height)/2));
  renderMapCamera();
  document.querySelector('#map-zoom-level').textContent=`${mapZoomLevels[mapZoomIndex]}%`;
  document.querySelector('#map-zoom-out').disabled=mapZoomIndex===0;
  document.querySelector('#map-zoom-in').disabled=mapZoomIndex===mapZoomLevels.length-1;
}

const mapCanvas=document.querySelector('#map-canvas');
mapCanvas.addEventListener('pointerdown',event=>{
  mapCamera.dragging=true;
  mapCamera.pointerX=event.clientX;
  mapCamera.pointerY=event.clientY;
  mapCanvas.setPointerCapture(event.pointerId);
  mapCanvas.classList.add('dragging');
});
mapCanvas.addEventListener('pointermove',event=>{
  if(!mapCamera.dragging) return;
  const bounds=mapCanvas.getBoundingClientRect();
  const dx=(event.clientX-mapCamera.pointerX)*mapCamera.width/bounds.width;
  const dy=(event.clientY-mapCamera.pointerY)*mapCamera.height/bounds.height;
  mapCamera.x=Math.max(0,Math.min(2754-mapCamera.width,mapCamera.x-dx));
  mapCamera.y=Math.max(0,Math.min(1398-mapCamera.height,mapCamera.y-dy));
  mapCamera.pointerX=event.clientX;
  mapCamera.pointerY=event.clientY;
  renderMapCamera();
});
function stopMapDrag(){mapCamera.dragging=false;mapCanvas.classList.remove('dragging')}
mapCanvas.addEventListener('pointerup',stopMapDrag);
mapCanvas.addEventListener('pointercancel',stopMapDrag);

function eventParts(event){
  if(typeof event==='string') return [event,null];
  const entry=Object.entries(event)[0];
  return entry||['Unknown',null];
}

function showExecutionEvent(event){
  const [kind,payload]=eventParts(event);
  let message=i18n.t('installing');
  if(kind==='Started') message=i18n.t('installStarted');
  else if(kind==='Warning') message=i18n.t('installWarning');
  else if(kind==='Failed') message=i18n.t('installFailed');
  else if(kind==='Completed') message=i18n.t('installCompleted');
  if(kind==='Warning'||kind==='Failed') console.error('Installer service event',payload);
  installStatusTitle.textContent=message;
}

function setInstallationStatus(state,title){
  installStatus.hidden=false;
  installStatus.className=`install-status ${state}`;
  installStatusTitle.textContent=title;
}

function lockWizard(locked){
  steps.forEach(step=>{step.disabled=locked;});
  back.disabled=locked||current===0;
}

async function executeInstallation(){
  const choice=buildGuidedChoice();
  if(!choice||!selectedPlan||!summaryConfigValid||!installConfirm.checked||installing||installationTerminal) return;

  installing=true;
  lockWizard(true);
  back.hidden=true;
  reboot.hidden=true;
  rebootError.hidden=true;
  setInstallationStatus('running',i18n.t('installAuthorizing'));
  updateInstallButtonState();
  updateNextButtonState();

  let stopListening=null;
  const streamedEvents=[];
  try{
    const config=collectInstallConfig();
    await invoke('validate_install_config',{config});
    stopListening=await listen('installation-event',event=>{
      streamedEvents.push(event.payload);
      showExecutionEvent(event.payload);
    });
    const events=await invoke('execute_plan',{request:{choice,plan:selectedPlan,config}});
    // Normally every item has already arrived through the live event. Keep
    // the command response as a fallback if WebKit missed the whole stream or
    // its final items while the privileged process was exiting.
    if(streamedEvents.length!==events.length){
      events.forEach(showExecutionEvent);
    }

    const failure=events.map(eventParts).find(([kind])=>kind==='Failed');
    const completed=events.map(eventParts).some(([kind])=>kind==='Completed');
    if(failure){
      installationTerminal=true;
      setInstallationStatus('failed',i18n.t('installFailed'));
      install.textContent=i18n.t('installFailed');
    }else if(completed){
      installationTerminal=true;
      installStatus.hidden=true;
      reboot.hidden=false;
      await fitWindowToMonitor();
    }else{
      throw new Error('installer service did not report completion');
    }
  }catch(error){
    console.error('Could not start installation',error);
    setInstallationStatus('failed',i18n.t('installFailed'));
    install.textContent=i18n.t('installRetry');
  }finally{
    if(stopListening) stopListening();
    installing=false;
    lockWizard(installationTerminal);
    back.hidden=installationTerminal;
    updateInstallButtonState();
    updateNextButtonState();
  }
}

async function restartSystem(){
  reboot.disabled=true;
  reboot.textContent=i18n.t('rebooting');
  rebootError.hidden=true;
  try{
    await invoke('restart_system');
  }catch(error){
    reboot.disabled=false;
    reboot.innerHTML=i18n.t('rebootLabel');
    rebootError.textContent=i18n.t('rebootFailed');
    rebootError.hidden=false;
  }
}

next.addEventListener('click',async()=>{if(installing||installationTerminal)return;if(current===4&&!validate())return;if(current===5&&!selectedPlan)return;if(current<6){if(current===5)await updateSummary();show(current+1)}});
back.addEventListener('click',()=>{if(!installing&&!installationTerminal&&current>0)show(current-1)});
steps.forEach(step=>step.addEventListener('click',()=>{const index=Number(step.dataset.step);if(!installing&&!installationTerminal&&index<=current)show(index)}));
installConfirm.addEventListener('change',updateInstallButtonState);
install.addEventListener('click',executeInstallation);
reboot.addEventListener('click',restartSystem);
window.addEventListener('resize',()=>{
  const currentScreenSize=`${screen.availWidth}x${screen.availHeight}`;
  if(currentScreenSize!==knownScreenSize){
    knownScreenSize=currentScreenSize;
    void fitWindowToMonitor();
  }
});
document.querySelectorAll('.choice input').forEach(input=>input.addEventListener('change',()=>{document.querySelectorAll('.choice').forEach(choice=>choice.classList.toggle('selected',choice.querySelector('input').checked))}));
document.querySelector('#keyboard-cards').addEventListener('change',event=>{if(event.target.matches('input'))document.querySelectorAll('.keyboard-card').forEach(card=>card.classList.toggle('selected',card.querySelector('input').checked))});
document.querySelector('#keyboard-search').addEventListener('input',event=>renderKeyboardCards(event.target.value));
document.querySelector('#language-cards').addEventListener('change',event=>{
  if(!event.target.matches('input')) return;
  selectedLocale=event.target.value;
  document.querySelectorAll('#language-cards .choice').forEach(card=>card.classList.toggle('selected',card.querySelector('input').checked));
  i18n.apply(uiLocale(event.target.value));
  renderLanguageCards(document.querySelector('#language-search').value);
  renderKeyboardCards(document.querySelector('#keyboard-search').value);
  renderDiskCards();
  if(selectedPlan) renderPlan(selectedPlan);
  show(current);
});
document.querySelector('#language-search').addEventListener('input',event=>renderLanguageCards(event.target.value));
document.querySelector('#timezone').addEventListener('change',event=>selectTimezone(event.target.value));
document.querySelector('#map-zoom-out').addEventListener('click',()=>setMapZoom(mapZoomIndex-1));
document.querySelector('#map-zoom-in').addEventListener('click',()=>setMapZoom(mapZoomIndex+1));
document.querySelector('#map-zoom-reset').addEventListener('click',()=>setMapZoom(0));
document.querySelector('#disk-list').addEventListener('change',event=>{
  if(!event.target.matches('input')) return;
  selectedDiskPath=event.target.value;
  renderDiskCards();
  refreshPlan();
});
document.querySelector('#swap-choice').addEventListener('change',event=>{
  if(!event.target.matches('input')) return;
  swapChoice=event.target.value;
  document.querySelectorAll('.swap-card').forEach(card=>card.classList.toggle('selected',card.querySelector('input').checked));
  refreshPlan();
});
let usernameManuallyEdited=false;
document.querySelector('#full-name').addEventListener('input',event=>{
  const username=document.querySelector('#username');
  if(!usernameManuallyEdited) username.value=suggestedUsername(event.target.value);
});
document.querySelector('#username').addEventListener('input',()=>{usernameManuallyEdited=true;});
i18n.apply('en-US');
setMapZoom(0);
void loadTimezones();
renderLanguageCards();
renderKeyboardCards();
loadInstallerLogo();
discoverStorage();
show(0);
void fitWindowToMonitor();
