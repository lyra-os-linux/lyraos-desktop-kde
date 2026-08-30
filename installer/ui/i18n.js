// Installer UI translations. Add a locale by registering one catalog here;
// missing keys always fall back to en-US so partial future translations do
// not leave blank controls or expose implementation keys to the user.
window.LyraI18n=(()=>{
  const catalogs={
    'en-US':{
      title:'Install Lyra OS',back:'← Back',next:'Continue <span>→</span>',step:'STEP {current} / 07',
      languageCount:'{count} languages available',noLanguages:'No languages found. Try another search.',
      keyboardCount:'{count} layouts available',noKeyboards:'No layouts found. Try another search.',
      keyboardGroup:{language:'Language',europe:'Europe',latinAmerica:'Latin America',nordic:'Nordic',cyrillic:'Cyrillic',middleEast:'Middle East',asia:'Asia',special:'Special',alternative:'Alternative'},
      diskCount:'{count} disk{s} detected',noDisks:'No disks were found in this session.',detectingDisks:'Detecting disks…',
      waitingInput:'Waiting for input',waitingSelection:'Waiting for selection',unknownTransport:'Unknown transport',
      diskNamed:'{transport} disk',diskGeneric:'Disk {name}',diskLiveMedia:'This is the live installation media and cannot be selected',diskRaidMember:'Already belongs to a RAID array',diskLvmMember:'Already belongs to an active LVM volume group',diskWillErase:'Existing partitions and data will be erased',diskAvailable:'Available for installation',
      espReuse:'Reuse the existing ESP at {path}',espCreate:'Create a new {size} ESP',swapNone:'No swap or ZRAM',swapZram:'ZRAM (compressed memory)',swapDisk:'Disk swap · {size}',planEfi:'EFI partition',planFilesystem:'Filesystem',planMemory:'Virtual memory',planBtrfs:'Btrfs · {count} subvolumes',planErased:'Data that will be erased during installation:',calculatingPlan:'Calculating the installation plan…',summarySwapDisk:'Disk swap (8 GiB)',confirmErase:'I understand that the data on {target} will be permanently erased.',
      erasedPartition:'{path}: {filesystem}{mount} ({size})',unknownFilesystem:'unknown filesystem',mountedAt:', mounted at {path}',
      installAuthorizing:'Authorizing and starting the installation…',installStarted:'Preparing the installation…',installing:'Installing Lyra OS…',
      installWarning:'The installer reported a warning',installFailed:'The installation was interrupted',installCompleted:'Installation and cleanup completed',installRetry:'Try installing again',
      storageDiscoveryFailed:'Could not inspect the available disks.',planFailed:'Could not calculate a safe installation plan.',
      rebootLabel:'Restart system <span aria-hidden="true">↻</span>',rebooting:'Restarting…',rebootFailed:'Could not restart the system',
      validation:{fullNameRequired:'Full name is required',invalidUsername:'Invalid username',invalidHostname:'Invalid device name',passwordTooShort:'The password must contain at least 8 characters',passwordMismatch:'The passwords do not match',unsupportedLocale:'Unsupported language',unsupportedTimezone:'Unsupported time zone',unsupportedKeyboard:'Unsupported keyboard layout'},
      static:{
        '.rail-footer':'<span class="status-dot"></span> Secure live session',
        '.step[data-step="0"]':'<span>01</span> Welcome','.step[data-step="1"]':'<span>02</span> Language','.step[data-step="2"]':'<span>03</span> Region','.step[data-step="3"]':'<span>04</span> Keyboard','.step[data-step="4"]':'<span>05</span> Your account','.step[data-step="5"]':'<span>06</span> Storage','.step[data-step="6"]':'<span>07</span> Summary',
        '[data-page="0"] .kicker':'A NEW BEGINNING','[data-page="0"] h1':'Install<br><em>Lyra OS.</em>','[data-page="0"] .lead':'A harmonious and secure desktop experience, designed to keep up with you.',
        '[data-page="1"] .kicker':'PERSONALIZATION','[data-page="1"] h1':'Speak your<br><em>language.</em>','[data-page="1"] .lead':'Choose the initial system language. You can change it later.',
        '[data-page="2"] .kicker':'LOCATION','[data-page="2"] h1':'Your place<br><em>in the world.</em>','[data-page="2"] .lead':'The region defines date, currency and number formats, and the suggested time zone.',
        '[data-page="3"] .kicker':'INPUT','[data-page="3"] h1':'Every key<br><em>in its place.</em>','[data-page="3"] .lead':'Choose your physical keyboard layout. You can add other layouts later in Settings.',
        '[data-page="4"] .kicker':'IDENTITY','[data-page="4"] h1':'Your space.<br><em>Your name.</em>','[data-page="4"] .lead':'Create the main Lyra OS account. It will have sudo access; root will remain locked.',
        '[data-page="5"] .kicker':'DESTINATION','[data-page="5"] h1':'Where will Lyra<br><em>live?</em>','[data-page="5"] .lead':'Choose the entire disk for the system and how Lyra should use virtual memory.',
        '[data-page="6"] .kicker':'ALMOST THERE','[data-page="6"] h1':'Ready to<br><em>begin.</em>','[data-page="6"] .lead':'Review your choices. When started, the selected destination will be erased and Lyra OS will be installed.',
        '.feature-item:nth-child(1) strong':'Rust core','.feature-item:nth-child(1) small':'Safe by design','.feature-item:nth-child(2) strong':'Security','.feature-item:nth-child(2) small':'Protection integrated into the system',
        '.map-hint':'Select a pin to set the time zone','.timezone-selection span':'Selected time zone','.region-preview span':'Regional preview','.keyboard-note':'<span>⌨</span> ABNT2 is recommended for physical keyboards sold in Brazil.','.storage-option-label':'VIRTUAL MEMORY',
        '.swap-card:nth-child(1) strong':'No swap','.swap-card:nth-child(1) small':'Does not create swap or enable ZRAM','.swap-card:nth-child(2) strong':'Disk swap','.swap-card:nth-child(2) small':'Dedicated 8 GiB partition','.swap-card:nth-child(3) small':'Compressed memory without using disk space',
        '.safe-note':'<span>✓</span> This step only reads the current disk state and calculates a plan — no destructive operation runs here.',
        '.summary-list div:nth-child(1) span':'Language','.summary-list div:nth-child(2) span':'Device','.summary-list div:nth-child(3) span':'Account','.summary-list div:nth-child(4) span':'Destination','.summary-list div:nth-child(5) span':'Virtual memory',
        '#back':'← Back','#next':'Continue <span>→</span>','#install':'Install Lyra OS','#reboot':'Restart system <span aria-hidden="true">↻</span>',
        '#install-status-title':'Preparing the installation…',
        '#install-confirm-text':'I understand that the destination data will be permanently erased.',
      },
      labels:{'.timezone-picker':'Time zone','.account-field:nth-child(1)':'Full name','.account-field:nth-child(2)':'Username','.account-field:nth-child(3)':'Device name','.account-field:nth-child(4)':'Password','.account-field:nth-child(5)':'Confirm password'},
      placeholders:{'#language-search':'Search languages…','#keyboard-search':'Search language, country or variant…','#full-name':'What should we call you?','#username':'Suggested from your full name','#password':'At least 8 characters','#password-confirm':'Repeat the password'},
      attributes:{'.rail|aria-label':'Installation progress','.brand-logo|alt':'Lyra Installer logo','.steps|aria-label':'Steps','.feature-strip|aria-label':'Lyra OS technologies','.welcome-art img|alt':'Lyra OS logo and the motto Harmony. Performance. Freedom.','.timezone-map|aria-label':'Select a time zone on the map','.map-zoom|aria-label':'Zoom controls','#map-zoom-out|aria-label':'Zoom out','#map-zoom-in|aria-label':'Zoom in','#map-zoom-reset|aria-label':'Reset zoom','.final-art img|alt':'Night landscape with the Lyra constellation and Lyra OS branding.'},
    },
    'pt-BR':{
      title:'Instalar o Lyra OS',back:'← Voltar',next:'Continuar <span>→</span>',step:'ETAPA {current} / 07',
      languageCount:'{count} idiomas disponíveis',noLanguages:'Nenhum idioma encontrado. Tente outro termo.',
      keyboardCount:'{count} layouts disponíveis',noKeyboards:'Nenhum layout encontrado. Tente outro termo.',
      keyboardGroup:{language:'Idioma',europe:'Europa',latinAmerica:'América Latina',nordic:'Nórdicos',cyrillic:'Cirílico',middleEast:'Oriente Médio',asia:'Ásia',special:'Especial',alternative:'Alternativos'},
      diskCount:'{count} disco{s} detectado{s}',noDisks:'Nenhum disco foi encontrado nesta sessão.',detectingDisks:'Detectando discos…',
      waitingInput:'Aguardando preenchimento',waitingSelection:'Aguardando seleção',unknownTransport:'Transporte desconhecido',
      diskNamed:'Disco {transport}',diskGeneric:'Disco {name}',diskLiveMedia:'É a mídia de instalação (live) — não pode ser destino',diskRaidMember:'Já é membro de um array RAID',diskLvmMember:'Já é um physical volume LVM em uso',diskWillErase:'Partições/dados existentes serão apagados',diskAvailable:'Disponível para instalação',
      espReuse:'ESP existente reaproveitada em {path}',espCreate:'Nova ESP de {size} será criada',swapNone:'Sem swap nem ZRAM',swapZram:'ZRAM (memória comprimida)',swapDisk:'Swap em disco · {size}',planEfi:'Partição EFI',planFilesystem:'Sistema de arquivos',planMemory:'Memória virtual',planBtrfs:'Btrfs · {count} subvolumes',planErased:'Dados que serão apagados nesta instalação:',calculatingPlan:'Calculando o plano de instalação…',summarySwapDisk:'Swap em disco (8 GiB)',confirmErase:'Entendo que os dados de {target} serão apagados permanentemente.',
      erasedPartition:'{path}: {filesystem}{mount} ({size})',unknownFilesystem:'sistema de arquivos desconhecido',mountedAt:', montado em {path}',
      installAuthorizing:'Autorizando e iniciando a instalação…',installStarted:'Preparando a instalação…',installing:'Instalando o Lyra OS…',
      installWarning:'O instalador emitiu um aviso',installFailed:'A instalação foi interrompida',installCompleted:'Instalação e limpeza concluídas',installRetry:'Tentar instalar novamente',
      storageDiscoveryFailed:'Não foi possível verificar os discos disponíveis.',planFailed:'Não foi possível calcular um plano de instalação seguro.',
      rebootLabel:'Reiniciar o sistema <span aria-hidden="true">↻</span>',rebooting:'Reiniciando…',rebootFailed:'Não foi possível reiniciar o sistema',
      validation:{fullNameRequired:'Nome completo obrigatório',invalidUsername:'Nome de usuário inválido',invalidHostname:'Nome do dispositivo inválido',passwordTooShort:'A senha deve ter ao menos 8 caracteres',passwordMismatch:'As senhas não coincidem',unsupportedLocale:'Idioma não suportado',unsupportedTimezone:'Fuso horário não suportado',unsupportedKeyboard:'Layout de teclado não suportado'},
      static:{
        '.rail-footer':'<span class="status-dot"></span> Sessão live segura',
        '.step[data-step="0"]':'<span>01</span> Boas-vindas','.step[data-step="1"]':'<span>02</span> Idioma','.step[data-step="2"]':'<span>03</span> Região','.step[data-step="3"]':'<span>04</span> Teclado','.step[data-step="4"]':'<span>05</span> Sua conta','.step[data-step="5"]':'<span>06</span> Armazenamento','.step[data-step="6"]':'<span>07</span> Resumo',
        '[data-page="0"] .kicker':'UM NOVO COMEÇO','[data-page="0"] h1':'Instale o<br><em>Lyra OS.</em>','[data-page="0"] .lead':'Uma experiência desktop harmoniosa, segura e feita para acompanhar o seu ritmo.',
        '[data-page="1"] .kicker':'PERSONALIZAÇÃO','[data-page="1"] h1':'Fale a sua<br><em>linguagem.</em>','[data-page="1"] .lead':'Escolha o idioma inicial do sistema. Você poderá mudar essa opção depois.',
        '[data-page="2"] .kicker':'LOCALIZAÇÃO','[data-page="2"] h1':'Seu lugar<br><em>no mundo.</em>','[data-page="2"] .lead':'A região define formatos de data, moeda, números e o fuso horário sugerido para o sistema.',
        '[data-page="3"] .kicker':'ENTRADA','[data-page="3"] h1':'Cada tecla<br><em>no lugar.</em>','[data-page="3"] .lead':'Escolha o layout físico do seu teclado. Você poderá adicionar outros layouts depois nas Configurações.',
        '[data-page="4"] .kicker':'IDENTIDADE','[data-page="4"] h1':'Seu espaço.<br><em>Seu nome.</em>','[data-page="4"] .lead':'Crie a conta principal do Lyra OS. Ela terá acesso administrativo via sudo; root permanecerá bloqueado.',
        '[data-page="5"] .kicker':'DESTINO','[data-page="5"] h1':'Onde o Lyra<br><em>vai viver?</em>','[data-page="5"] .lead':'Escolha o disco inteiro que receberá o sistema e como o Lyra deve usar memória virtual.',
        '[data-page="6"] .kicker':'QUASE LÁ','[data-page="6"] h1':'Pronto para<br><em>começar.</em>','[data-page="6"] .lead':'Revise suas escolhas. Ao iniciar, o destino selecionado será apagado e o Lyra OS será instalado de verdade.',
        '.feature-item:nth-child(1) strong':'Rust no núcleo','.feature-item:nth-child(1) small':'Seguro por construção','.feature-item:nth-child(2) strong':'Segurança','.feature-item:nth-child(2) small':'Proteção integrada ao sistema',
        '.map-hint':'Selecione um pin para definir o fuso horário','.timezone-selection span':'Fuso horário selecionado','.region-preview span':'Prévia regional','.keyboard-note':'<span>⌨</span> O layout recomendado para teclados físicos vendidos no Brasil é ABNT2.','.storage-option-label':'MEMÓRIA VIRTUAL',
        '.swap-card:nth-child(1) strong':'Sem swap','.swap-card:nth-child(1) small':'Não cria swap nem ativa ZRAM','.swap-card:nth-child(2) strong':'Swap em disco','.swap-card:nth-child(2) small':'Partição dedicada de 8 GiB','.swap-card:nth-child(3) small':'Memória comprimida, sem ocupar o disco',
        '.safe-note':'<span>✓</span> Esta etapa apenas lê o estado atual dos discos e calcula um plano — nenhuma operação destrutiva é executada aqui.',
        '.summary-list div:nth-child(1) span':'Idioma','.summary-list div:nth-child(2) span':'Dispositivo','.summary-list div:nth-child(3) span':'Conta','.summary-list div:nth-child(4) span':'Destino','.summary-list div:nth-child(5) span':'Memória virtual',
        '#back':'← Voltar','#next':'Continuar <span>→</span>','#install':'Instalar o Lyra OS','#reboot':'Reiniciar o sistema <span aria-hidden="true">↻</span>',
        '#install-status-title':'Preparando a instalação…',
        '#install-confirm-text':'Entendo que os dados do destino serão apagados permanentemente.',
      },
      labels:{'.timezone-picker':'Fuso horário','.account-field:nth-child(1)':'Nome completo','.account-field:nth-child(2)':'Nome de usuário','.account-field:nth-child(3)':'Nome do dispositivo','.account-field:nth-child(4)':'Senha','.account-field:nth-child(5)':'Confirmar senha'},
      placeholders:{'#language-search':'Buscar idioma…','#keyboard-search':'Buscar idioma, país ou variante…','#full-name':'Como devemos chamar você?','#username':'Sugerido a partir do nome completo','#password':'Mínimo de 8 caracteres','#password-confirm':'Repita a senha'},
      attributes:{'.rail|aria-label':'Progresso da instalação','.brand-logo|alt':'Logo do Lyra Installer','.steps|aria-label':'Etapas','.feature-strip|aria-label':'Tecnologias do Lyra OS','.welcome-art img|alt':'Logotipo do Lyra OS e o lema Harmonia. Performance. Liberdade.','.timezone-map|aria-label':'Selecione um fuso horário no mapa','.map-zoom|aria-label':'Controles de zoom','#map-zoom-out|aria-label':'Reduzir mapa','#map-zoom-in|aria-label':'Ampliar mapa','#map-zoom-reset|aria-label':'Restaurar zoom','.final-art img|alt':'Paisagem noturna com a constelação de Lyra e a marca Lyra OS.'},
    },
    'es-ES':{
      title:'Instalar Lyra OS',back:'← Atrás',next:'Continuar <span>→</span>',step:'PASO {current} / 07',
      languageCount:'{count} idiomas disponibles',noLanguages:'No se encontraron idiomas. Prueba otra búsqueda.',
      keyboardCount:'{count} distribuciones disponibles',noKeyboards:'No se encontraron distribuciones. Prueba otra búsqueda.',
      keyboardGroup:{language:'Idioma',europe:'Europa',latinAmerica:'América Latina',nordic:'Nórdicos',cyrillic:'Cirílico',middleEast:'Oriente Medio',asia:'Asia',special:'Especial',alternative:'Alternativos'},
      diskCount:'{count} disco{s} detectado{s}',noDisks:'No se encontraron discos en esta sesión.',detectingDisks:'Detectando discos…',
      waitingInput:'Pendiente de completar',waitingSelection:'Pendiente de selección',unknownTransport:'Transporte desconocido',
      diskNamed:'Disco {transport}',diskGeneric:'Disco {name}',diskLiveMedia:'Es el medio de instalación live y no puede seleccionarse',diskRaidMember:'Ya pertenece a un conjunto RAID',diskLvmMember:'Ya pertenece a un grupo de volúmenes LVM activo',diskWillErase:'Se borrarán las particiones y los datos existentes',diskAvailable:'Disponible para la instalación',
      espReuse:'Reutilizar la ESP existente en {path}',espCreate:'Crear una nueva ESP de {size}',swapNone:'Sin swap ni ZRAM',swapZram:'ZRAM (memoria comprimida)',swapDisk:'Swap en disco · {size}',planEfi:'Partición EFI',planFilesystem:'Sistema de archivos',planMemory:'Memoria virtual',planBtrfs:'Btrfs · {count} subvolúmenes',planErased:'Datos que se borrarán durante la instalación:',calculatingPlan:'Calculando el plan de instalación…',summarySwapDisk:'Swap en disco (8 GiB)',confirmErase:'Entiendo que los datos de {target} se borrarán permanentemente.',
      erasedPartition:'{path}: {filesystem}{mount} ({size})',unknownFilesystem:'sistema de archivos desconocido',mountedAt:', montado en {path}',
      installAuthorizing:'Autorizando e iniciando la instalación…',installStarted:'Preparando la instalación…',installing:'Instalando Lyra OS…',
      installWarning:'El instalador emitió una advertencia',installFailed:'La instalación fue interrumpida',installCompleted:'Instalación y limpieza completadas',installRetry:'Intentar instalar de nuevo',
      storageDiscoveryFailed:'No se pudieron consultar los discos disponibles.',planFailed:'No se pudo calcular un plan de instalación seguro.',
      rebootLabel:'Reiniciar el sistema <span aria-hidden="true">↻</span>',rebooting:'Reiniciando…',rebootFailed:'No se pudo reiniciar el sistema',
      validation:{fullNameRequired:'El nombre completo es obligatorio',invalidUsername:'Nombre de usuario no válido',invalidHostname:'Nombre del dispositivo no válido',passwordTooShort:'La contraseña debe tener al menos 8 caracteres',passwordMismatch:'Las contraseñas no coinciden',unsupportedLocale:'Idioma no compatible',unsupportedTimezone:'Zona horaria no compatible',unsupportedKeyboard:'Distribución de teclado no compatible'},
      static:{
        '.rail-footer':'<span class="status-dot"></span> Sesión live segura',
        '.step[data-step="0"]':'<span>01</span> Bienvenida','.step[data-step="1"]':'<span>02</span> Idioma','.step[data-step="2"]':'<span>03</span> Región','.step[data-step="3"]':'<span>04</span> Teclado','.step[data-step="4"]':'<span>05</span> Tu cuenta','.step[data-step="5"]':'<span>06</span> Almacenamiento','.step[data-step="6"]':'<span>07</span> Resumen',
        '[data-page="0"] .kicker':'UN NUEVO COMIENZO','[data-page="0"] h1':'Instala<br><em>Lyra OS.</em>','[data-page="0"] .lead':'Una experiencia de escritorio armoniosa y segura, diseñada para acompañarte.',
        '[data-page="1"] .kicker':'PERSONALIZACIÓN','[data-page="1"] h1':'Habla tu<br><em>idioma.</em>','[data-page="1"] .lead':'Elige el idioma inicial del sistema. Podrás cambiarlo más tarde.',
        '[data-page="2"] .kicker':'UBICACIÓN','[data-page="2"] h1':'Tu lugar<br><em>en el mundo.</em>','[data-page="2"] .lead':'La región define los formatos y la zona horaria sugerida para el sistema.',
        '[data-page="3"] .kicker':'ENTRADA','[data-page="3"] h1':'Cada tecla<br><em>en su lugar.</em>','[data-page="3"] .lead':'Elige la distribución física del teclado. Podrás añadir otras más tarde.',
        '[data-page="4"] .kicker':'IDENTIDAD','[data-page="4"] h1':'Tu espacio.<br><em>Tu nombre.</em>','[data-page="4"] .lead':'Crea la cuenta principal de Lyra OS. Tendrá acceso sudo; root seguirá bloqueado.',
        '[data-page="5"] .kicker':'DESTINO','[data-page="5"] h1':'¿Dónde vivirá<br><em>Lyra?</em>','[data-page="5"] .lead':'Elige el disco completo y cómo utilizar la memoria virtual.',
        '[data-page="6"] .kicker':'CASI LISTO','[data-page="6"] h1':'Todo listo para<br><em>empezar.</em>','[data-page="6"] .lead':'Revisa tus opciones. El destino seleccionado se borrará al iniciar.',
        '.feature-item:nth-child(1) strong':'Núcleo en Rust','.feature-item:nth-child(1) small':'Seguro por diseño','.feature-item:nth-child(2) strong':'Seguridad','.feature-item:nth-child(2) small':'Protección integrada en el sistema',
        '.map-hint':'Selecciona una zona horaria en la lista','.timezone-selection span':'Zona horaria seleccionada','.region-preview span':'Vista previa regional','.keyboard-note':'<span>⌨</span> Elige la distribución correspondiente a tu teclado físico.','.storage-option-label':'MEMORIA VIRTUAL',
        '.swap-card:nth-child(1) strong':'Sin swap','.swap-card:nth-child(1) small':'No crea swap ni activa ZRAM','.swap-card:nth-child(2) strong':'Swap en disco','.swap-card:nth-child(2) small':'Partición dedicada de 8 GiB','.swap-card:nth-child(3) small':'Memoria comprimida sin usar espacio en disco',
        '.safe-note':'<span>✓</span> Este paso solo lee los discos y calcula un plan; no ejecuta operaciones destructivas.',
        '.summary-list div:nth-child(1) span':'Idioma','.summary-list div:nth-child(2) span':'Dispositivo','.summary-list div:nth-child(3) span':'Cuenta','.summary-list div:nth-child(4) span':'Destino','.summary-list div:nth-child(5) span':'Memoria virtual',
        '#back':'← Atrás','#next':'Continuar <span>→</span>','#install':'Instalar Lyra OS','#reboot':'Reiniciar el sistema <span aria-hidden="true">↻</span>','#install-confirm-text':'Entiendo que los datos del destino se borrarán permanentemente.',
        '#install-status-title':'Preparando la instalación…',
      },
      labels:{'.timezone-picker':'Zona horaria','.account-field:nth-child(1)':'Nombre completo','.account-field:nth-child(2)':'Nombre de usuario','.account-field:nth-child(3)':'Nombre del dispositivo','.account-field:nth-child(4)':'Contraseña','.account-field:nth-child(5)':'Confirmar contraseña'},
      placeholders:{'#language-search':'Buscar idiomas…','#keyboard-search':'Buscar idioma, país o variante…','#full-name':'¿Cómo debemos llamarte?','#username':'Sugerido a partir del nombre completo','#password':'Mínimo 8 caracteres','#password-confirm':'Repite la contraseña'},
      attributes:{'.rail|aria-label':'Progreso de la instalación','.brand-logo|alt':'Logotipo de Lyra Installer','.steps|aria-label':'Pasos','.feature-strip|aria-label':'Tecnologías de Lyra OS','.welcome-art img|alt':'Logotipo de Lyra OS y el lema Armonía. Rendimiento. Libertad.','.timezone-map|aria-label':'Selecciona una zona horaria en el mapa','.map-zoom|aria-label':'Controles de zoom','#map-zoom-out|aria-label':'Reducir mapa','#map-zoom-in|aria-label':'Ampliar mapa','#map-zoom-reset|aria-label':'Restablecer zoom','.final-art img|alt':'Paisaje nocturno con la constelación de Lyra y la marca Lyra OS.'},
    },
  };
  let current='en-US';
  const interpolate=(value,vars={})=>String(value).replace(/\{(\w+)\}/g,(_,key)=>vars[key]??`{${key}}`);
  function lookup(catalog,key){return key.split('.').reduce((value,part)=>value?.[part],catalog)}
  function t(key,vars={}){return interpolate(lookup(catalogs[current],key)??lookup(catalogs['en-US'],key)??key,vars)}
  function apply(locale){
    current=catalogs[locale]?locale:'en-US';
    document.documentElement.lang=current;
    document.title=t('title');
    const merged={...catalogs['en-US'].static,...catalogs[current].static};
    Object.entries(merged).forEach(([selector,value])=>{const element=document.querySelector(selector);if(element)element.innerHTML=value});
    const placeholders={...catalogs['en-US'].placeholders,...catalogs[current].placeholders};
    Object.entries(placeholders).forEach(([selector,value])=>{const element=document.querySelector(selector);if(element)element.placeholder=value});
    const labels={...catalogs['en-US'].labels,...catalogs[current].labels};
    Object.entries(labels).forEach(([selector,value])=>{const element=document.querySelector(selector);if(element&&element.firstChild)element.firstChild.textContent=value});
    const attributes={...catalogs['en-US'].attributes,...catalogs[current].attributes};
    Object.entries(attributes).forEach(([entry,value])=>{const [selector,name]=entry.split('|');const element=document.querySelector(selector);if(element)element.setAttribute(name,value)});
  }
  function register(locale,catalog){catalogs[locale]=catalog}
  return {apply,t,register,get locale(){return current}};
})();
