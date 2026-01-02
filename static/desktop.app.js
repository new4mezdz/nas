axios.defaults.withCredentials = true;
const { createApp } = Vue;

createApp({
  data() {
  return {
    loggedIn: false, // 保留这个
user: { username: '', is_admin: false, avatar: '' },

    // ========== 桌面系统 ==========
    windows: [],
    nextWindowId: 1,
    maxZIndex: 100,
    dragging: null,
    // ========== 搜索 ==========
searchQuery: '',
    searchBarOpen: false,

    // ========== 任务栏 ==========
    showStartMenu: false,
    currentTime: '',
  canRead: true,   // 添加这个
        canWrite: true,  // 添加这个
        canDelete: true,
    // ========== 右键菜单 ==========
    contextMenu: {
      show: false,
      x: 0,
      y: 0,
      items: []
    },

    // ========== 系统数据 ==========
    systemInfo: {},
    disks: [],
    availableDrives: [],
    ecStatus: { is_configured: false },
    encryptionStatus: [],


    encryptionProgress: {
      show: false,
      percent: 0,
      status: 'running',  // running | complete | error
      title: ''
    },
    // ========== 文件上传 ==========
    showUploadDialog: false,
    uploadFiles: [],
    dragOver: false,
    uploadStatus: '',
    currentUploadWindow: null,

    // ===== [修正] EC配置对话框状态 (放到正确的位置) =====
    showEcSetupDialog: false,
    ecSetupForm: {
      k: 4,
      m: 2,
      selectedDisks: [],
      capacityEstimate: null,
      error: ''
    },
    // 空间池状态
    poolEncryptionStatus: {},  // 池加密状态
poolStatus: { is_configured: false },
    poolHealth: null,  // 新增
poolAvailableDisks: [],  // 新增
showAddDiskDialog: false,  // 新增
showRebalanceDialog: false,  // 新增
rebalancePreview: null,  // 新增


// 空间池配置对话框
showPoolSetupDialog: false,
poolSetupForm: {
  name: '主存储池',
  selectedDisks: [],
  availableDisks: [],
  error: ''
},
     // ========== 桌面背景 ==========
    desktopBg: localStorage.getItem('desktopBg') || 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    showBgSettings: false,
    bgPresets: [
      { name: '默认紫色', value: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' },
      { name: '深蓝', value: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)' },
      { name: '日落', value: 'linear-gradient(135deg, #ff6b6b 0%, #feca57 100%)' },
      { name: '森林', value: 'linear-gradient(135deg, #134e5e 0%, #71b280 100%)' },
      { name: '星空', value: 'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)' },
      { name: '海洋', value: 'linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%)' },
      { name: '玫瑰', value: 'linear-gradient(135deg, #ee9ca7 0%, #ffdde1 100%)' },
      { name: '暗黑', value: 'linear-gradient(135deg, #232526 0%, #414345 100%)' }
    ],
    customBgUrl: '',

// 逻辑卷配置对话框
showVolumeDialog: false,
volumeForm: {
  name: '',
  display_name: '',
  icon: '📁',
  strategy: 'largest_free',
  error: ''
},

// 可选图标列表
volumeIcons: ['📁', '🎬', '📄', '🎵', '🖼️', '🎮', '💼', '📦', '🔧', '📚'],
// ========== 应用列表 ==========
appList: [
  { name: '文件管理', icon: '📁', keywords: ['文件', '文件管理', 'file', 'files'], action: 'openFilesWindow', adminOnly: false },
  { name: '系统信息', icon: '📊', keywords: ['系统', '系统信息', 'system'], action: 'openSystemWindow', adminOnly: false },
  { name: '磁盘管理', icon: '💿', keywords: ['磁盘', '硬盘', 'disk'], action: 'openDiskWindow', adminOnly: true },
  { name: '空间池', icon: '📦', keywords: ['空间池', 'pool', '存储池'], action: 'openPoolWindow', adminOnly: true },
  { name: '桌面背景', icon: '🖼️', keywords: ['背景', '壁纸', 'background'], action: 'openBgSettings', adminOnly: false },
  { name: '个人设置', icon: '⚙️', keywords: ['设置', '个人', 'settings'], action: 'openPersonalSettings', adminOnly: false },
],
      searchSelectedIndex: 0,
  };
},

  watch: {
      searchQuery() {
  this.searchSelectedIndex = 0;
},
    'ecSetupForm.selectedDisks': {
      deep: true,
      handler() { this.getEcCapacityEstimate(); }
    },
    'ecSetupForm.k'() {
      this.getEcCapacityEstimate();
    }
  },

  methods: {
    // ==========================================
  // 在 methods 中添加
async getEcCapacityEstimate() {
    const { k, selectedDisks } = this.ecSetupForm;
    if (k > 0 && selectedDisks.length > 0) {
        try {
            // 调用我们即将创建的后端API
            const res = await axios.post('/api/ec_estimate', { k, disks: selectedDisks });
            this.ecSetupForm.capacityEstimate = res.data;
        } catch (error) {
            console.error("容量预估失败:", error);
            this.ecSetupForm.capacityEstimate = null;
        }
    } else {
        this.ecSetupForm.capacityEstimate = null;
    }
},

async doSearch() {
  if (!this.searchQuery.trim()) return;

  // 如果有匹配的应用且选中了应用项，打开应用
  if (this.matchedApps.length > 0 && this.searchSelectedIndex < this.matchedApps.length) {
    this.openMatchedApp(this.matchedApps[this.searchSelectedIndex]);
    return;
  }

  // 否则搜索文件
  this.doFileSearch();
},

openMatchedApp(app) {
  this.searchQuery = '';
  this.searchBarOpen = false;
  this.searchSelectedIndex = 0;

  if (app.action === 'openBgSettings') {
    this.showBgSettings = true;
  } else {
    this[app.action]();
  }
  this.showToast(`✅ 打开: ${app.name}`, 'success');
},

async doFileSearch() {
  this.showToast(`🔍 正在搜索文件: ${this.searchQuery}...`, 'info');
  const keyword = this.searchQuery;
  this.searchBarOpen = false;
  this.searchSelectedIndex = 0;

  try {
    const response = await axios.get('/api/search_global', {
      params: { keyword: keyword, limit: 200 }
    });

    if (response.data.success) {
      const results = response.data.items || [];

      if (results.length === 0) {
        this.showToast(`未找到包含 "${keyword}" 的文件`, 'warning');
        this.searchQuery = '';
        return;
      }

      const storageList = this.buildStorageList();
      this.createWindow('files', `搜索结果: ${keyword}`, '🔍', {
        width: 1100,
        height: 700,
        sidebar: { storage: storageList, favorites: [], recent: [] },
        currentDrive: 'search',
        currentPath: `搜索: "${keyword}"`,
        files: results,
        selectedFiles: [],
        viewMode: 'list',
        history: [],
        historyIndex: 0,
        clipboard: { mode: null, items: [], sourceDrive: null, sourcePath: null },
        searchKeyword: keyword,
        isSearching: false,
        isSearchMode: true,
        searchResults: results,
        sortBy: 'name',
        sortOrder: 'asc'
      });

      this.showToast(`✅ 找到 ${results.length} 个文件`, 'success');
      this.searchQuery = '';
    } else {
      this.showToast(response.data.error || '搜索失败', 'error');
    }
  } catch (e) {
    console.error('搜索失败:', e);
    this.showToast('搜索失败: ' + (e.response?.data?.error || e.message), 'error');
  }
},

handleSearchKeydown(e) {
  const totalItems = this.matchedApps.length + 1; // 应用数 + 搜索文件选项
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    this.searchSelectedIndex = (this.searchSelectedIndex + 1) % totalItems;
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    this.searchSelectedIndex = (this.searchSelectedIndex - 1 + totalItems) % totalItems;
  }
},

    logout() {
  // 清除本地状态
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  this.loggedIn = false;
  this.user = { username: '', is_admin: false };
  this.windows = [];
  this.showStartMenu = false;
  delete axios.defaults.headers.common['Authorization'];

  // ✅ 跳转到管理端登录页
  window.close();
},
    setDesktopBg(bg) {
      this.desktopBg = bg;
      localStorage.setItem('desktopBg', bg);
    },

    // 上传背景图片
    uploadBgImage(event) {
      const file = event.target.files[0];
      if (!file) return;

      if (!file.type.startsWith('image/')) {
        alert('请选择图片文件');
        return;
      }

      const reader = new FileReader();
      reader.onload = (e) => {
        const bg = `url(${e.target.result}) center/cover no-repeat`;
        this.setDesktopBg(bg);
        this.showBgSettings = false;
      };
      reader.readAsDataURL(file);
    },

    setCustomBg() {
      if (this.customBgUrl.trim()) {
        const bg = `url(${this.customBgUrl}) center/cover no-repeat`;
        this.setDesktopBg(bg);
        this.customBgUrl = '';
      }
    },

    // ==========================================
    // 数据加载
    // ==========================================
    async loadData() {
      try {
        await Promise.all([
          this.fetchSystemInfo(),
          this.fetchDiskInfo(),
          this.fetchAvailableDrives(),
          this.fetchEcStatus(),
          this.fetchEncryptionStatus(),
            this.fetchPoolEncryptionStatus(),
            this.fetchPoolStatus()
        ]);
      } catch (e) {
        console.error('加载数据失败:', e);
        if (e.response?.status === 401) {
          this.logout();
        }
      }
    },

  async fetchSystemInfo() {
  try {
    const res = await axios.get('/api/system');
    this.systemInfo = res.data;
  } catch (e) {
    console.error('获取系统信息失败:', e);
  }
},

    async fetchDiskInfo() {
      try {
        const res = await axios.get('/api/disk');
        this.disks = res.data;
      } catch (e) {
        console.error('获取磁盘信息失败:', e);
      }
    },
    async fetchEncryptionStatus() {
    try {
        const response = await axios.get('/api/encryption/status', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });
        if (response.data) {
            this.encryptionStatus = response.data;  // 直接使用 response.data,不要 .drives
        }
    } catch (error) {
        console.error('获取加密状态失败:', error);
        this.encryptionStatus = [];
    }
},
    async fetchAvailableDrives() {
      try {
        const res = await axios.get('/api/drives');
        this.availableDrives = res.data;
      } catch (e) {
        console.error('获取可用驱动器失败:', e);
      }
    },

    async fetchEcStatus() {
    try {
        const response = await axios.get('/api/ec_status', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });
        if (response.data) {
            this.ecStatus = response.data;  // 这个保持对象
        }
    } catch (error) {
        console.error('获取纠删码状态失败:', error);
        this.ecStatus = { is_configured: false };  // 改这里,设为对象
    }
},


    // 在 createWindow 方法中添加初始化
createWindow(type, title, icon, data = {}) {
  const window = {
    id: this.nextWindowId++,
    type,
    title,
    icon,
    x: 100 + (this.windows.length * 30),
    y: 50 + (this.windows.length * 30),
    width: 900,
    height: 650,
    zIndex: ++this.maxZIndex,
    maximized: false,
    minimized: false,
    ...data
  };

  // 为设置窗口添加表单数据
  if (type === 'settings') {
    window.passwordForm = {
      oldPassword: '',
      newPassword: '',
      confirmPassword: ''
    };
  }

  this.windows.push(window);
  this.showStartMenu = false;
  return window;
},


    closeWindow(id) {
  const win = this.windows.find(w => w.id === id);
  if (win && win.refreshTimer) {
    clearInterval(win.refreshTimer);
  }
  this.windows = this.windows.filter(w => w.id !== id);
},

    minimizeWindow(id) {
      const window = this.windows.find(w => w.id === id);
      if (window) window.minimized = true;
    },

    toggleMaximize(id) {
      const window = this.windows.find(w => w.id === id);
      if (window) window.maximized = !window.maximized;
    },

    focusWindow(id) {
      const window = this.windows.find(w => w.id === id);
      if (window) {
        window.zIndex = ++this.maxZIndex;
        window.minimized = false;
      }
    },

    startDrag(event, window) {
      if (window.maximized) return;

      this.dragging = {
        window,
        startX: event.clientX - window.x,
        startY: event.clientY - window.y
      };

      const onMove = (e) => {
        if (this.dragging) {
          this.dragging.window.x = e.clientX - this.dragging.startX;
          this.dragging.window.y = e.clientY - this.dragging.startY;
        }
      };

      const onUp = () => {
        this.dragging = null;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },

    // ==========================================
    // 文件管理器
    // ==========================================

    openFilesWindow(initialPath = null) {
      const storageList = this.buildStorageList();

      // 如果没有指定路径,默认显示第一个存储设备
      let currentDrive, currentPath;
      if (initialPath) {
        if (initialPath === 'ec_volume' || initialPath.startsWith('ec_volume')) {
          currentDrive = 'ec_volume';
          currentPath = 'ec_volume';
        } else {
          currentDrive = initialPath;
          currentPath = '/';
        }
      } else {
        // 默认选择第一个存储设备
        currentDrive = storageList[0]?.path || 'D:/';
        currentPath = storageList[0]?.path === 'ec_volume' ? 'ec_volume' : '/';
      }

      const window = this.createWindow('files', '文件管理', '📁', {
        width: 1100,
        height: 700,
        sidebar: {
          storage: storageList,
          favorites: [],
          recent: []
        },
        currentDrive: currentDrive,
        currentPath: currentPath,
        files: [],
        selectedFiles: [],
        viewMode: 'list',
        history: [{ drive: currentDrive, path: currentPath }],
        historyIndex: 0,
        clipboard: {
          mode: null,
          items: [],
          sourceDrive: null,
          sourcePath: null
        },
        searchKeyword: '',
isSearching: false,
isSearchMode: false,
searchResults: [],
        sortBy: 'name',
        sortOrder: 'asc'
      });

      this.loadFiles(window);
      return window;
    },

   buildStorageList() {
  const storage = [];

  console.log('[DEBUG] ecStatus:', this.ecStatus);
  console.log('[DEBUG] is_configured:', this.ecStatus.is_configured);
  console.log('[DEBUG] config_disks:', this.ecStatus.config_disks);
  console.log('[DEBUG] config_disks 内容:', JSON.stringify(this.ecStatus.config_disks));

  // ✅ 标准化 config_disks 路径格式：统一转为大写的正斜杠格式
  const normalizedConfigDisks = this.ecStatus.config_disks?.map(d =>
    d.toUpperCase().replace(/\\/g, '/')
  ) || [];
  console.log('[DEBUG] 标准化后的 config_disks:', normalizedConfigDisks);

  // 添加物理磁盘
this.availableDrives.forEach(drive => {
  console.log('[DEBUG] 检查磁盘:', drive.drive);

  // ✅ 跳过纠删码磁盘
  if (this.ecStatus.is_configured &&
      normalizedConfigDisks.includes(drive.drive)) {
    console.log('[DEBUG] ✅ 跳过纠删码磁盘:', drive.drive);
    return;
  }

  // ✅ 【新增】跳过已加入空间池的磁盘
if (this.poolStatus.is_configured && this.poolStatus.disks) {
  const normalizedPoolDisks = this.poolStatus.disks.map(d =>
  (d.path || d.disk || d).toString().toUpperCase().replace(/\\/g, '/')
);
  const normalizedDrive = drive.drive.toUpperCase().replace(/\\/g, '/');
  if (normalizedPoolDisks.includes(normalizedDrive)) {
    console.log('[DEBUG] ✅ 跳过空间池磁盘:', drive.drive);
    return;
  }
}


    const diskInfo = this.disks.find(d => d.mount === drive.drive);
    const driveLabel = drive.drive.replace(':/', '');
    const encStatus = this.encryptionStatus.find(s => s.drive === drive.drive);

    let icon = '💾';
    if (encStatus?.is_configured) {
        icon = encStatus.is_unlocked ? '🔓' : '🔒';
    }

    storage.push({
      icon: icon,
      label: `${driveLabel} 盘`,
      path: drive.drive,
      type: 'physical',
      usage: diskInfo ? diskInfo.percent : 0,
    });
  });

  // 添加空间池逻辑卷
if (this.poolStatus.is_configured && this.poolStatus.volumes) {
  Object.entries(this.poolStatus.volumes).forEach(([volName, volConfig]) => {
    storage.push({
      icon: volConfig.icon || '📦',
      label: volConfig.display_name,
      path: `pool://${volName}`,
      type: 'pool_volume',
      usage: 0,
      volumeName: volName
    });
  });
}
  // 添加 EC 卷
  if (this.ecStatus.is_configured) {
    storage.unshift({
      icon: '🛡️',
      label: '纠删码卷',
      path: 'ec_volume',
      type: 'ec',
      usage: 0
    });
  }

  console.log('[DEBUG] 最终存储列表:', storage);
  return storage;
},


// 打开个人设置
openPersonalSettings() {
  const window = this.createWindow('settings', '个人设置', '⚙️', {
    width: 600,
    height: 500,
    currentTab: 'profile' // profile, password
  });
  this.showStartMenu = false;
},



    async loadFiles(window) {
  window.isLocked = false; // 每次加载前重置状态
  const token = localStorage.getItem('token');
  if (!token) {
    this.showToast('未登录', 'error');
    return;
  }

  // ==============================
  // 🟢 新增: 处理收藏夹视图
  // ==============================
  if (window.currentDrive === 'favorites') {
    try {
      const res = await axios.get('/api/favorites');
      window.files = res.data.items || [];
      window.currentPath = '收藏夹';
      this.sortFiles(window);
      return;
    } catch (e) {
      console.error('加载收藏夹失败:', e);
      this.showToast('加载收藏夹失败', 'error');
      return;
    }
  }

  // ==============================
  // 🟢 新增: 处理最近访问视图
  // ==============================
  if (window.currentDrive === 'recent') {
    try {
      const res = await axios.get('/api/recent');
      window.files = res.data.items || [];
      window.currentPath = '最近访问';
      this.sortFiles(window);
      return;
    } catch (e) {
      console.error('加载最近访问失败:', e);
      this.showToast('加载最近访问失败', 'error');
      return;
    }
  }

  // ==============================
  // 🟡 原有逻辑: 处理普通文件路径
  // ==============================
  let fullPath;
  if (window.currentDrive === 'ec_volume') {
    fullPath = window.currentPath.startsWith('ec_volume') ? window.currentPath : 'ec_volume';
  } else if (window.currentDrive.startsWith('pool://')) {
    const cleanPath = window.currentPath.replace(/^\//, '');
    fullPath = cleanPath ? `${window.currentDrive}/${cleanPath}` : window.currentDrive;
  } else {
    const cleanPath = window.currentPath.replace(/^\//, '');
    fullPath = window.currentDrive + cleanPath;
  }

  try {
    const response = await axios.get(`/api/list?path=${encodeURIComponent(fullPath)}`);
    window.files = response.data.items || [];
    this.sortFiles(window);
  } catch (error) {
    console.error('加载文件列表失败:', error);
    const errorData = error.response?.data || {};
    const errorMsg = errorData.error || '未知错误';
    const errorType = errorData.error_type;

    // ✅ 根据错误类型做不同处理
    if (errorType === 'disk_locked' || errorType === 'pool_locked') {
      window.isLocked = true;
      window.files = [];
      const lockTarget = errorData.drive || errorData.volume || '存储';

      this.showToast(`🔒 ${errorMsg}`, 'warning');

      // 自动弹出解锁对话框
      setTimeout(async () => {
        const shouldUnlock = confirm(`${lockTarget} 已锁定\n\n是否立即解锁?`);
        if (shouldUnlock) {
          if (errorType === 'pool_locked') {
            // 池或卷锁定，弹出解锁对话框
            const password = prompt('请输入密码解锁:');
            if (password) {
              try {
                const volume = errorData.volume;
                // 先尝试解锁卷，再尝试解锁池
                let res = await axios.post('/api/pool/unlock', { type: 'volume', name: volume, password });
                if (!res.data.success) {
                  res = await axios.post('/api/pool/unlock', { type: 'pool', name: 'main', password });
                }
                if (res.data.success) {
                  this.showToast('✅ 解锁成功', 'success');
                  await this.fetchPoolEncryptionStatus();
                  this.loadFiles(window);
                } else {
                  this.showToast('❌ 密码错误', 'error');
                }
              } catch (e) {
                this.showToast('解锁失败: ' + (e.response?.data?.error || e.message), 'error');
              }
            }
          } else {
            // 磁盘锁定
            await this.unlockDisk(errorData.drive, window);
          }
        }
      }, 100);
    } else {
      this.showToast(`❌ 加载失败: ${errorMsg}`, 'error');
    }
  }
},
    // 2. 添加记录最近访问的方法
async addToRecent(file, window) {
  try {
    // 如果已经在“最近访问”列表中，就不需要构建路径了，直接用 file.path
    // 但为了统一，我们重新构建完整路径
    let fullPath = file.path; // 收藏夹和最近访问接口返回的数据里有 path

    // 如果是在普通视图中，需要构建路径
    if (window.currentDrive !== 'favorites' && window.currentDrive !== 'recent') {
        fullPath = this.buildFullPath(window, file.name);
    }

    await axios.post('/api/recent/add', {
      path: fullPath,
      name: file.name,
      is_dir: file.is_dir
    });
  } catch (e) {
    console.error('添加到最近访问失败', e);
  }
},

    sortFiles(window) {
      const files = window.files;
      const sortBy = window.sortBy;
      const order = window.sortOrder === 'asc' ? 1 : -1;

      files.sort((a, b) => {
        if (a.is_dir !== b.is_dir) {
          return a.is_dir ? -1 : 1;
        }

        let comparison = 0;
        switch (sortBy) {
          case 'name':
            comparison = a.name.localeCompare(b.name);
            break;
          case 'size':
            comparison = (a.size || 0) - (b.size || 0);
            break;
          case 'mtime':
            comparison = (a.mtime || 0) - (b.mtime || 0);
            break;
        }

        return comparison * order;
      });
    },

    toggleSort(window, field) {
      if (window.sortBy === field) {
        window.sortOrder = window.sortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        window.sortBy = field;
        window.sortOrder = 'asc';
      }
      this.sortFiles(window);
    },

    navigateToStorage(window, storagePath) {
      window.currentDrive = storagePath;
      window.currentPath = storagePath === 'ec_volume' ? 'ec_volume' : '/';
      window.selectedFiles = [];
      this.addToHistory(window);
      this.loadFiles(window);
    },

    openFolder(window, folderName) {
      let newPath;
      if (window.currentDrive === 'ec_volume') {
        if (window.currentPath === 'ec_volume') {
          newPath = 'ec_volume/' + folderName;
        } else {
          newPath = window.currentPath + '/' + folderName;
        }
      } else {
        if (window.currentPath === '/') {
          newPath = '/' + folderName;
        } else {
          newPath = window.currentPath + '/' + folderName;
        }
      }

      window.currentPath = newPath;
      window.selectedFiles = [];
      this.addToHistory(window);
      this.loadFiles(window);
    },

    goParent(window) {
      if (window.currentPath === '/' || window.currentPath === 'ec_volume') return;

      let parts;
      if (window.currentDrive === 'ec_volume') {
        parts = window.currentPath.split('/').filter(p => p && p !== 'ec_volume');
        parts.pop();
        window.currentPath = parts.length > 0 ? 'ec_volume/' + parts.join('/') : 'ec_volume';
      } else {
        parts = window.currentPath.split('/').filter(p => p);
        parts.pop();
        window.currentPath = parts.length > 0 ? '/' + parts.join('/') : '/';
      }

      window.selectedFiles = [];
      this.addToHistory(window);
      this.loadFiles(window);
    },

    goBack(window) {
      if (window.historyIndex > 0) {
        window.historyIndex--;
        const historyItem = window.history[window.historyIndex];
        window.currentDrive = historyItem.drive;
        window.currentPath = historyItem.path;
        window.selectedFiles = [];
        this.loadFiles(window);
      }
    },

    goForward(window) {
      if (window.historyIndex < window.history.length - 1) {
        window.historyIndex++;
        const historyItem = window.history[window.historyIndex];
        window.currentDrive = historyItem.drive;
        window.currentPath = historyItem.path;
        window.selectedFiles = [];
        this.loadFiles(window);
      }
    },

    addToHistory(window) {
      window.history = window.history.slice(0, window.historyIndex + 1);
      window.history.push({
        drive: window.currentDrive,
        path: window.currentPath
      });
      window.historyIndex = window.history.length - 1;

      if (window.history.length > 50) {
        window.history.shift();
        window.historyIndex--;
      }
    },

    refreshFiles(window) {
      window.selectedFiles = [];
      this.loadFiles(window);
    },

    toggleFileSelection(window, fileName, event) {
      if (event.ctrlKey || event.metaKey) {
        const index = window.selectedFiles.indexOf(fileName);
        if (index > -1) {
          window.selectedFiles.splice(index, 1);
        } else {
          window.selectedFiles.push(fileName);
        }
      } else if (event.shiftKey && window.selectedFiles.length > 0) {
        const lastSelected = window.selectedFiles[window.selectedFiles.length - 1];
        const lastIndex = window.files.findIndex(f => f.name === lastSelected);
        const currentIndex = window.files.findIndex(f => f.name === fileName);

        const start = Math.min(lastIndex, currentIndex);
        const end = Math.max(lastIndex, currentIndex);

        window.selectedFiles = window.files
          .slice(start, end + 1)
          .map(f => f.name);
      } else {
        window.selectedFiles = [fileName];
      }
    },

    selectAllFiles(window) {
      window.selectedFiles = window.files.map(f => f.name);
    },

    clearSelection(window) {
      window.selectedFiles = [];
    },

   handleDoubleClick(window, file) {

   if (window.isSearchMode) {
        this.openSearchResult(window, file);
        return;
    }

  // 如果当前是在 收藏夹 或 最近访问 视图中
  if (window.currentDrive === 'favorites' || window.currentDrive === 'recent') {
      if (file.is_dir) {
          // 跳转到该文件夹所在的真实路径
          this.jumpToLocation(window, file.path);
      } else {
          // 记录最近访问并预览
          this.addToRecent(file, window);
          // 对于文件，我们也需要知道它的真实 window 上下文来构建 API 请求
          // 这里我们做一个特殊的临时处理，或者修改 previewFile 支持绝对路径
          // 简单的做法：修改 previewFile 让它支持直接传 path
          this.previewFile(window, file, file.path);
      }
      return;
  }

  // 原有逻辑
  if (file.is_dir) {
    this.openFolder(window, file.name);
  } else {
    this.addToRecent(file, window); // <--- 添加这行
    const ext = file.name.split('.').pop().toLowerCase();
    if (['xlsx', 'docx'].includes(ext)) {
  this.openUniverEditor(file, window);
} else {
  this.previewFile(window, file);
}
  }
},

    jumpToLocation(window, fullPath) {
    // 解析 fullPath，设置 window.currentDrive 和 window.currentPath
    // 假设 fullPath 格式为 "D:/data/docs" 或 "ec_volume/photos"

    if (fullPath.startsWith('ec_volume')) {
        window.currentDrive = 'ec_volume';
        window.currentPath = fullPath;
    } else if (fullPath.startsWith('pool://')) {
        const parts = fullPath.split('/'); // pool://pool1/sub
        window.currentDrive = parts.slice(0, 3).join('/'); // pool://pool1
        window.currentPath = '/' + parts.slice(3).join('/');
    } else {
        // 物理盘 D:/xxx
        const driveMatch = fullPath.match(/^([a-zA-Z]:\/|\/)/);
        if (driveMatch) {
            window.currentDrive = driveMatch[0]; // D:/
            window.currentPath = fullPath.substring(window.currentDrive.length);
            if (!window.currentPath.startsWith('/')) window.currentPath = '/' + window.currentPath;
        }
    }

    this.loadFiles(window);
},
    async toggleFavorite(window, file) {
    const fullPath = window.currentDrive === 'favorites' || window.currentDrive === 'recent'
        ? file.path
        : this.buildFullPath(window, file.name);

    try {
        // 先检查是否已收藏 (这里简化逻辑，如果是在收藏夹视图，肯定是移除)
        if (window.currentDrive === 'favorites') {
             await axios.post('/api/favorites/remove', { path: fullPath });
             this.showToast('🗑️ 已取消收藏', 'success');
             this.loadFiles(window); // 刷新列表
             return;
        }

        // 检查状态 (为了交互更好，可以先 check 接口，或者直接用 add/remove)
        // 这里为了简单，我们做成“添加到收藏”
        await axios.post('/api/favorites/add', {
            path: fullPath,
            name: file.name,
            is_dir: file.is_dir
        });
        this.showToast('⭐ 已添加到收藏夹', 'success');

    } catch (e) {
        this.showToast('操作失败: ' + e.message, 'error');
    }
},
   buildFullPath(window, fileName) {
  if (window.currentDrive === 'ec_volume') {
    let path = window.currentPath.replace(/\\/g, '/');
    path = path.replace(/^ec_volume\/?/, '');
    path = path.replace(/^\//, '').replace(/\/$/, '');

    if (path === '') {
      return `ec_volume/${fileName}`;
    }
    return `ec_volume/${path}/${fileName}`;
  } else if (window.currentDrive.startsWith('pool://')) {
    // 空间池卷：pool://volume_name/subpath/filename
    let cleanPath = (window.currentPath || '').replace(/^\//, '').replace(/\/$/, '');
    if (cleanPath === '' || cleanPath === '/') {
      return window.currentDrive + '/' + fileName;
    }
    return window.currentDrive + '/' + cleanPath + '/' + fileName;
  } else {
    let cleanPath = (window.currentPath || '').replace(/^\//, '');
    if (cleanPath === '' || cleanPath === '/') {
      return window.currentDrive + fileName;
    }
    return window.currentDrive + cleanPath + '/' + fileName;
  }
},

    downloadFile(win, file) {
  // 收藏夹/最近访问视图使用 file.path，其他情况构建路径
  const fullPath = (win.currentDrive === 'favorites' || win.currentDrive === 'recent')
    ? file.path
    : this.buildFullPath(win, file.name);
  const token = localStorage.getItem('token');
  const url = `${axios.defaults.baseURL || ''}/api/download?path=${encodeURIComponent(fullPath)}&token=${encodeURIComponent(token)}`;
  // 直接调用全局的 window.open()，或者省略 window. 也是一样的效果
  window.open(url);
},
    downloadSelected(window) {
      if (window.selectedFiles.length === 0) {
        alert('请先选择要下载的文件');
        return;
      }

      if (window.selectedFiles.length === 1) {
        const file = window.files.find(f => f.name === window.selectedFiles[0]);
        if (file && !file.is_dir) {
          this.downloadFile(window, file);
        } else {
          alert('无法下载文件夹');
        }
      } else {
        alert(`批量下载功能开发中...\n已选择 ${window.selectedFiles.length} 个文件`);
      }
    },


renameSelected(window) {
  if (window.selectedFiles.length !== 1) {
    this.showToast('⚠️ 请选择一个文件或文件夹进行重命名', 'warning');
    return;
  }

  const fileName = window.selectedFiles[0];
  const file = window.files.find(f => f.name === fileName);

  if (!file) {
    this.showToast('❌ 文件不存在', 'error');
    return;
  }


  this.renameFile(window, file);
},

    async deleteSelected(window) {
  if (window.selectedFiles.length === 0) {
    alert('请先选择要删除的文件');
    return;
  }

  const count = window.selectedFiles.length;
  if (!confirm(`确认删除选中的 ${count} 项?`)) {
    return;
  }

  // 构建所有要删除的路径
  const selectedPaths = window.selectedFiles.map(fileName =>
    this.buildFullPath(window, fileName)
  );

  try {
    const response = await fetch((axios.defaults.baseURL || '') + '/api/batch_delete', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({ paths: selectedPaths })
    });

    const data = await response.json();

    if (data.success) {
      alert(`成功删除 ${count} 项`);
      this.loadFiles(window);
      window.selectedFiles = [];
    } else {
      alert(`删除失败: ${data.errors ? data.errors.join(', ') : '未知错误'}`);
    }
  } catch (error) {
    alert(`删除失败: ${error.message}`);
  }
},

    cutSelected(window) {
      if (window.selectedFiles.length === 0) {
        alert('请先选择要剪切的文件');
        return;
      }

      window.clipboard = {
        mode: 'cut',
        items: [...window.selectedFiles],
        sourceDrive: window.currentDrive,
        sourcePath: window.currentPath
      };

      alert(`已剪切 ${window.selectedFiles.length} 项`);
    },

    copySelected(window) {
      if (window.selectedFiles.length === 0) {
        alert('请先选择要复制的文件');
        return;
      }

      window.clipboard = {
        mode: 'copy',
        items: [...window.selectedFiles],
        sourceDrive: window.currentDrive,
        sourcePath: window.currentPath
      };

      alert(`已复制 ${window.selectedFiles.length} 项`);
    },

    openUploadDialog(window) { // 假设这是您的方法
        if (!this.canWrite) {
            this.showToast('权限不足，无法上传文件', 'error');
            return;
        }
        this.currentUploadWindow = window; //
        this.showUploadDialog = true; //
    },
// 重命名文件/文件夹
async renameFile(window, file, newName) {
  const oldName = typeof file === 'string' ? file : file.name;
  const isDir = typeof file === 'object' && file.is_dir;

  // 分离文件名和后缀
  let baseName = oldName;
  let ext = '';
  if (!isDir) {
    const lastDot = oldName.lastIndexOf('.');
    if (lastDot > 0) {
      baseName = oldName.substring(0, lastDot);
      ext = oldName.substring(lastDot);  // 包含点，如 ".mp4"
    }
  }

  // 如果没有提供新名称，弹出输入框（只显示文件名部分）
  if (!newName) {
    const inputName = prompt(`请输入新名称:${ext ? '\n(后缀 ' + ext + ' 将自动保留)' : ''}`, baseName);
    if (!inputName || !inputName.trim()) {
      return;
    }
    newName = inputName.trim() + ext;  // 自动补上后缀
  }

  // 名称没有变化
  if (newName === oldName) {
    this.closeContextMenu();
    return;
  }

  // 检查文件名是否包含非法字符
  if (/[<>:"/\\|?*]/.test(newName)) {
    this.showToast('❌ 文件名包含非法字符', 'error');
    this.closeContextMenu();
    return;
  }

  try {
    // 构建完整路径
    const fullPath = this.buildFullPath(window, oldName);

    // 发送重命名请求
    const response = await axios.post('/api/rename', {
      path: fullPath,
      new_name: newName
    });

    if (response.data.success) {
      this.showToast(`✅ 重命名成功: ${oldName} → ${newName}`, 'success');
      // 刷新文件列表
      this.loadFiles(window);
      // 清除选中状态
      window.selectedFiles = [];
    } else {
      this.showToast(`❌ 重命名失败: ${response.data.error}`, 'error');
    }
  } catch (error) {
    console.error('重命名失败:', error);
    const errorMsg = error.response?.data?.error || error.message;
    this.showToast(`❌ 重命名失败: ${errorMsg}`, 'error');
  }

  this.closeContextMenu();
},
    // 新建文件夹
async createNewFolder(window) { // 假设这是您的方法
        if (!this.canWrite) {
            this.showToast('权限不足，无法创建文件夹', 'error');
            return;
        }
        const folderName = prompt('请输入新文件夹名称:', '新文件夹'); //
        if (!folderName) return; //

        try {
            const path = this.buildFullPath(window, folderName); //
            // 注意: 后端 NAS 节点的 mkdir API 可能需要 parent 和 name 参数
            // 请确保后端 /api/mkdir 接口与此处的调用匹配
            // const parentPath = window.path; // 获取当前窗口路径
            // await axios.post('/api/mkdir', { parent: parentPath, name: folderName });
             await axios.post('/api/mkdir', { path: path }); // 假设您的 API 接受 path

            this.showToast('✅ 文件夹创建成功', 'success');
            this.loadFiles(window); //
        } catch (error) {
            console.error("创建文件夹失败:", error);
            this.showToast('❌ 创建失败: ' + (error.response?.data?.error || error.message), 'error'); //
        }
    },


  toggleSidebar() {
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.sidebar-overlay');

  if (sidebar && overlay) {
    sidebar.classList.toggle('show');
    overlay.classList.toggle('show');
  }
},

// 关闭侧边栏
closeSidebar() {
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.sidebar-overlay');

  if (sidebar && overlay) {
    sidebar.classList.remove('show');
    overlay.classList.remove('show');
  }
},

async encryptFileOrFolder(window, file) {
  const itemType = file.is_dir ? '文件夹' : '文件';

  // 弹出密码输入框
  const password = prompt(`请输入加密密码（用于加密${itemType}"${file.name}"）：`);
  if (!password) {
    this.showToast('❌ 未输入密码，操作已取消', 'info');
    return;
  }

  // 确认密码
  const confirmPassword = prompt('请再次输入密码以确认：');
  if (password !== confirmPassword) {
    this.showToast('❌ 两次输入的密码不一致', 'error');
    return;
  }

  this.closeContextMenu();

  try {
    const fullPath = this.buildFullPath(window, file.name);

    this.showToast(`🔄 正在加密${itemType}...`, 'info');

    const response = await axios.post('/api/file/encrypt', {
      file_path: fullPath,
      password: password,
      is_folder: file.is_dir
    });

    if (response.data.success) {
      this.showToast(`✅ ${response.data.message}`, 'success');

      // 显示详细结果（如果是文件夹）
      if (file.is_dir && response.data.details) {
        const details = response.data.details;
        if (details.failed > 0) {
          console.warn('部分文件加密失败:', details.errors);
        }
      }

      // 刷新文件列表
      await this.loadFiles(window);
    } else {
      this.showToast('❌ 加密失败', 'error');
    }
  } catch (error) {
    console.error('加密失败:', error);
    const errorMsg = error.response?.data?.error || error.message;
    this.showToast(`❌ 加密失败: ${errorMsg}`, 'error');
  }
},

async decryptFileOrFolder(window, file) {
  const itemType = file.is_dir ? '文件夹' : '文件';

  // 弹出密码输入框
  const password = prompt(`请输入解密密码（用于解密${itemType}"${file.name}"）：`);
  if (!password) {
    this.showToast('❌ 未输入密码，操作已取消', 'info');
    return;
  }

  this.closeContextMenu();

  try {
    const fullPath = this.buildFullPath(window, file.name);

    this.showToast(`🔄 正在解密${itemType}...`, 'info');

    const response = await axios.post('/api/file/decrypt', {
      file_path: fullPath,
      password: password,
      is_folder: file.is_dir
    });

    if (response.data.success) {
      this.showToast(`✅ ${response.data.message}`, 'success');

      // 显示详细结果（如果是文件夹）
      if (file.is_dir && response.data.details) {
        const details = response.data.details;
        if (details.failed > 0) {
          console.warn('部分文件解密失败:', details.errors);
          this.showToast(`⚠️ 部分文件解密失败，请查看控制台`, 'warning');
        }
      }

      // 刷新文件列表
      await this.loadFiles(window);
    } else {
      this.showToast('❌ 解密失败', 'error');
    }
  } catch (error) {
    console.error('解密失败:', error);
    const errorMsg = error.response?.data?.error || error.message;
    this.showToast(`❌ 解密失败: ${errorMsg}`, 'error');
  }
},

    async uploadDraggedFiles() {
      if (!this.uploadFiles.length) return;

      const window = this.currentUploadWindow;
      if (!window) return;

      let uploadPath;
if (window.currentDrive === 'ec_volume') {
  uploadPath = window.currentPath.startsWith('ec_volume')
    ? window.currentPath
    : 'ec_volume';
} else if (window.currentDrive.startsWith('pool://')) {
  // 空间池卷：pool://volume_name + /subpath
  const cleanPath = window.currentPath.replace(/^\//, '');
  uploadPath = cleanPath ? window.currentDrive + '/' + cleanPath : window.currentDrive;
} else {
  const cleanPath = window.currentPath.replace(/^\//, '');
  uploadPath = cleanPath ? window.currentDrive + cleanPath : window.currentDrive;
}

      uploadPath = uploadPath.replace(/\\/g, '/');
// 只清理路径部分的多余斜杠，保留 pool:// 协议头
if (uploadPath.startsWith('pool://')) {
  uploadPath = 'pool://' + uploadPath.slice(7).replace(/\/{2,}/g, '/');
} else {
  uploadPath = uploadPath.replace(/\/{2,}/g, '/');
}

      const token = localStorage.getItem('token');

      for (const file of this.uploadFiles) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('path', uploadPath);

        try {
          const res = await fetch((axios.defaults.baseURL || '') + '/api/upload', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`
            },
            body: formData
          });
          const data = await res.json();
          if (data.success) {
            this.uploadStatus = `✅ ${file.name} 上传成功`;
            this.loadFiles(window);
          } else {
            this.uploadStatus = `❌ ${file.name} 上传失败:${data.error}`;
          }
        } catch (err) {
          this.uploadStatus = `❌ ${file.name} 上传异常:${err.message}`;
        }
      }

      setTimeout(() => {
        this.uploadStatus = '';
        this.uploadFiles = [];
        this.showUploadDialog = false;
      }, 1200);
    },

    handleDrop(event) {
      this.dragOver = false;
      const files = Array.from(event.dataTransfer.files);
      if (files.length) {
        this.uploadFiles = files;
        this.uploadDraggedFiles();
      }
    },

    handleFileInputChange(event) {
      const files = Array.from(event.target.files);
      if (files.length) {
        this.uploadFiles = files;
        this.uploadDraggedFiles();
      }
    },




showFileContextMenu(event, file, win) {
    event.preventDefault();

    // 1. 获取扩展名
    const ext = file.name.split('.').pop().toLowerCase();
    const isEncrypted = file.name.endsWith('.encrypted');

    // 2. 定义基础菜单项
    const menuItems = [
        {
            icon: file.is_dir ? '📂' : '👁️',
            label: file.is_dir ? '打开' : '预览',
            action: () => {
                if (file.is_dir) {
                    this.handleDoubleClick(win, file);
                } else {
    // 收藏夹/最近访问视图传入完整路径
    const overridePath = (win.currentDrive === 'favorites' || win.currentDrive === 'recent') ? file.path : null;
    this.previewFile(win, file, overridePath);
}
                this.closeContextMenu();
            },
            disabled: !this.canRead || isEncrypted
        },
        {
            icon: '📥',
            label: '下载',
            action: () => {
                this.downloadFile(win, file);
                this.closeContextMenu();
            },
            disabled: !this.canRead || file.is_dir || isEncrypted
        },
        {
            icon: '🔗',
            label: '分享',
            action: () => {
                this.shareFile(win, file);
                this.closeContextMenu();
            },
            disabled: !this.canRead || file.is_dir || isEncrypted
        },
        // ✅ [新增] 收藏夹功能
        {
            icon: '⭐',
            // 如果当前是在收藏夹视图，显示"取消收藏"，否则显示"收藏"
            label: win.currentDrive === 'favorites' ? '取消收藏' : '收藏',
            action: () => {
                this.toggleFavorite(win, file);
                this.closeContextMenu();
            }
            // 收藏功能通常不需要特殊权限，只要能看到文件即可
        }
    ];

    // ✅ 文档编辑/预览入口 (Excel + Word + PPT)
    // ✅ 新格式 - 支持协作编辑
if (['xlsx', 'docx'].includes(ext)) {
    menuItems.push({
        icon: ext === 'xlsx' ? '📊' : '📄',
        label: ext === 'xlsx' ? '表格编辑' : '文档编辑',
        action: () => {
            this.openUniverEditor(file, win);
            this.closeContextMenu();
        },
        disabled: !this.canRead || isEncrypted
    });
}



    // 3. 通用文件操作
    menuItems.push(
        { separator: true },
        {
            icon: '✂️',
            label: '剪切',
            action: () => {
                this.cutFile(win, file);
                this.closeContextMenu();
            },
            disabled: !this.canWrite
        },
        {
            icon: '📋',
            label: '复制',
            action: () => {
                this.copyFile(win, file);
                this.closeContextMenu();
            },
            disabled: !this.canRead
        },
        { separator: true },
        {
            icon: '✏️',
            label: '重命名',
            action: () => {
                this.renameFile(win, file);
                this.closeContextMenu();
            },
            disabled: !this.canWrite
        },
        {
            icon: '🗑️',
            label: '删除',
            action: () => {
                this.deleteFile(win, file);
            },
            disabled: !this.canDelete
        },
        { separator: true },
        {
            icon: isEncrypted ? '🔓' : '🔒',
            label: isEncrypted ? '解密文件' : '加密文件',
            action: () => {
                if (isEncrypted) {
                    this.decryptFileOrFolder(win, file);
                } else {
                    this.encryptFileOrFolder(win, file);
                }
                this.closeContextMenu();
            },
            disabled: !this.canDelete
        }
    );

    // 4. 计算显示位置
    const menuWidth = 200;
    let menuHeight = 16;
    menuItems.forEach(item => {
        menuHeight += item.separator ? 1 : 44;
    });

    let x = event.clientX;
    let y = event.clientY;
    const availableHeight = window.innerHeight - 50;
    const availableWidth = window.innerWidth;

    if (availableWidth < 768) { x = 10; }
    else if (x + menuWidth > availableWidth - 20) { x = x - menuWidth - 10; }
    else { x = x + 10; }
    if (x < 10) x = 10;

    if (y + menuHeight > availableHeight) { y = y - menuHeight; }
    if (y < 50) y = 50;
    if (y + menuHeight > availableHeight) { y = availableHeight - menuHeight - 10; }

    this.contextMenu = { show: true, x, y, items: menuItems };
},

    showEmptyAreaContextMenu(event, window) {
      event.preventDefault();

      this.contextMenu = {
        show: true,
        x: event.clientX,
        y: event.clientY,
        items: [
          { icon: '📁', label: '新建文件夹', action: () => this.createNewFolder(window) },
          { icon: '📤', label: '上传文件', action: () => this.openUploadDialog(window) },
          { separator: true },
          {
            icon: '📋',
            label: '粘贴',
            action: () => this.pasteFiles(window),
            disabled: !window.clipboard.items.length
          },
          { separator: true },
          { icon: '🔄', label: '刷新', action: () => this.refreshFiles(window) }
        ]
      };
    },

    isDocumentFile(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const docTypes = ['docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'txt'];
  return docTypes.includes(ext);
},

    showDesktopMenu(event) {
      this.contextMenu = {
        show: true,
        x: event.clientX,
        y: event.clientY,
        items: [
          { icon: '📁', label: '打开文件管理', action: () => this.openFilesWindow() },
          { separator: true },
          { icon: '🔄', label: '刷新桌面', action: () => this.loadData() }
        ]
      };
    },

    showFilesIconMenu(event) {
      this.contextMenu = {
        show: true,
        x: event.clientX,
        y: event.clientY,
        items: [
          { icon: '📂', label: '打开', action: () => this.openFilesWindow() },
          { separator: true },
          { icon: '🔄', label: '刷新', action: () => this.loadData() }
        ]
      };
    },

    showFileMenu(event, drive) {
      this.contextMenu = {
        show: true,
        x: event.clientX,
        y: event.clientY,
        items: [
          { icon: '📂', label: '打开', action: () => this.openFilesWindow(drive.drive) }
        ]
      };
    },

    showECMenu(event) {
      this.contextMenu = {
        show: true,
        x: event.clientX,
        y: event.clientY,
        items: [
          { icon: '📂', label: '打开', action: () => this.openFilesWindow('ec_volume') },
          { separator: true },
          { icon: '⚙️', label: '配置', action: () => this.openECConfig() }
        ]
      };
    },

    closeContextMenu() {
      this.contextMenu.show = false;
    },

    cutFile(window, file) {
      window.clipboard = {
        mode: 'cut',
        items: [file.name],
        sourceDrive: window.currentDrive,
        sourcePath: window.currentPath
      };
      this.closeContextMenu();
    },

    copyFile(window, file) {
      window.clipboard = {
        mode: 'copy',
        items: [file.name],
        sourceDrive: window.currentDrive,
        sourcePath: window.currentPath
      };
      this.closeContextMenu();
    },

    async pasteFiles(window) {
      if (!window.clipboard.items.length) {
        this.showToast('ℹ️ 剪贴板为空', 'info');
        return;
      }
      if (!this.canWrite) {
          this.showToast('❌ 权限不足，无法粘贴', 'error');
          return;
      }

      const { mode, items, sourceDrive, sourcePath } = window.clipboard;
      const targetDrive = window.currentDrive;
      const targetPath = window.currentPath;

      // 1. 检查是否在同一目录进行无意义操作
      if (mode === 'cut' && sourceDrive === targetDrive && sourcePath === targetPath) {
        this.showToast('ℹ️ 源目录和目标目录相同', 'info');
        window.clipboard = { mode: null, items: [], sourceDrive: null, sourcePath: null };
        this.closeContextMenu();
        return;
      }

      // 检查复制到同目录
      if (mode === 'copy' && sourceDrive === targetDrive && sourcePath === targetPath) {
        this.showToast('ℹ️ 暂不支持在同一位置粘贴副本', 'info');
        // (未来可以实现 "file (copy).txt")
        return;
      }

      this.showToast(`🚀 正在 ${mode === 'cut' ? '移动' : '复制'} ${items.length} 个项目...`, 'info');

      let successCount = 0;
      let failCount = 0;
      const failedItems = [];

      for (const itemName of items) {
  try {
    // 2. 构建源路径
    let sourceFullPath;
    if (sourceDrive === 'ec_volume') {
      const path = sourcePath.replace(/^ec_volume\/?/, '').replace(/\/$/, '');
      sourceFullPath = path ? `ec_volume/${path}/${itemName}` : `ec_volume/${itemName}`;
    } else if (sourceDrive.startsWith('pool://')) {
      const cleanPath = (sourcePath || '').replace(/^\//, '').replace(/\/$/, '');
      sourceFullPath = cleanPath ? `${sourceDrive}/${cleanPath}/${itemName}` : `${sourceDrive}/${itemName}`;
    } else {
      const cleanPath = sourcePath.replace(/^\//, '');
      sourceFullPath = cleanPath ? `${sourceDrive}${cleanPath}/${itemName}` : `${sourceDrive}${itemName}`;
    }

    // 3. 构建目标路径
    let targetFullPath;
    if (targetDrive === 'ec_volume') {
      const path = targetPath.replace(/^ec_volume\/?/, '').replace(/\/$/, '');
      targetFullPath = path ? `ec_volume/${path}/${itemName}` : `ec_volume/${itemName}`;
    } else if (targetDrive.startsWith('pool://')) {
      const cleanPath = (targetPath || '').replace(/^\//, '').replace(/\/$/, '');
      targetFullPath = cleanPath ? `${targetDrive}/${cleanPath}/${itemName}` : `${targetDrive}/${itemName}`;
    } else {
      const cleanPath = targetPath.replace(/^\//, '');
      targetFullPath = cleanPath ? `${targetDrive}${cleanPath}/${itemName}` : `${targetDrive}${itemName}`;
    }


          // 5. 选择API
          const apiUrl = mode === 'cut' ? '/api/move' : '/api/copy';

         const response = await axios.post(apiUrl, {
  source_path: sourceFullPath.replace(/([^:])\/\//g, '$1/'),
  target_path: targetFullPath.replace(/([^:])\/\//g, '$1/')
});
          if (response.data.success) {
            successCount++;
          } else {
            failCount++;
            failedItems.push(`${itemName} (${response.data.error})`);
          }
        } catch (error) {
          failCount++;
          failedItems.push(`${itemName} (${error.response?.data?.error || error.message})`);
        }
      }

      // 6. 报告结果
      if (failCount > 0) {
        this.showToast(`⚠️ 操作完成: 成功 ${successCount}, 失败 ${failCount}`, 'warning');
        console.error("粘贴失败详情:", failedItems);
      } else {
        this.showToast(`✅ 操作成功: ${successCount} 个项目已${mode === 'cut' ? '移动' : '复制'}`, 'success');
      }

      // 7. 清理剪贴板
      window.clipboard = { mode: null, items: [], sourceDrive: null, sourcePath: null };

      // 8. 刷新当前窗口
      this.loadFiles(window);

      // 9. 如果是移动，并且源窗口还开着，也刷新源窗口
      if (mode === 'cut' && sourceDrive) {
        const sourceWindow = this.windows.find(w => w.type === 'files' && w.currentDrive === sourceDrive && w.currentPath === sourcePath);
        if (sourceWindow && sourceWindow.id !== window.id) {
          this.loadFiles(sourceWindow);
        }
      }

      this.closeContextMenu();
    },



    async deleteFile(window, file) { // 这是您提供的函数签名
      // 1. [新增] 前端权限检查 (使用计算属性)
      if (!this.canDelete) {
          this.showToast('权限不足，无法删除文件', 'error'); // 使用 showToast 显示错误
          this.closeContextMenu(); // 关闭右键菜单
          return;
      }

      // 保留确认对话框
      if (!confirm(`确认删除 ${file.name}?`)) { //
        this.closeContextMenu(); //
        return;
      }

      try {
        // 假设 this.buildFullPath 是您用于构建完整路径的辅助函数
        const fullPath = this.buildFullPath(window, file.name); //

        // 2. [修改] 使用 axios 并移除 Authorization header
        //    确保 /api/delete 是您后端 NAS 节点上正确的删除 API 路由
        const response = await axios.post('/api/delete', { // 改为 axios
             path: fullPath //
        });
        // axios 对于非 2xx 响应会自动抛出错误, 所以直接检查 data

        if (response.data.success) { //
          this.showToast('✅ 删除成功', 'success'); // 使用 showToast
          this.loadFiles(window); // 重新加载文件列表
        } else {
          // 如果后端返回 success: false 但状态码是 2xx (理论上不应该)
          this.showToast('❌ 删除失败: ' + (response.data.error || '未知错误'), 'error'); //
        }
      } catch (error) {
        // 处理 axios 抛出的错误 (网络问题, 或后端返回 4xx/5xx 状态码)
        console.error("删除文件时出错:", error);
        this.showToast('❌ 删除失败: ' + (error.response?.data?.error || error.message), 'error'); //
      }

      this.closeContextMenu(); //
    },

    // 文件类型检查辅助方法
    isImage(file) {
      return /\.(jpg|jpeg|png|gif|bmp|webp|svg)$/i.test(file.name);
    },

    isVideo(file) {
      return /\.(mp4|webm|ogg|mov|avi)$/i.test(file.name);
    },

    isAudio(file) {
      return /\.(mp3|wav|flac|m4a)$/i.test(file.name);
    },

    isPdf(file) {
      return /\.pdf$/i.test(file.name);
    },

    isText(file) {
      return /\.(txt|log|md|py|js|html|css|json)$/i.test(file.name);
    },
    isOffice(file) {
  return /\.(doc|docx|xls|xlsx|ppt|pptx)$/i.test(file.name);
},
    isPreviewable(file) {
  return this.isImage(file) || this.isVideo(file) || this.isAudio(file) ||
         this.isPdf(file) || this.isText(file) || this.isOffice(file);
},

    // 文件: static/desktop.app.js

async previewFile(window, file, overridePath = null) {
  if (file.is_dir) {
    alert('无法预览文件夹');
    return;
  }
  if (!this.isPreviewable(file)) {
    alert(`不支持预览此文件格式`);
    return;
  }
  // 收藏夹/最近访问会传入 overridePath，否则构建路径
  const fullPath = overridePath || this.buildFullPath(window, file.name);
  const token = localStorage.getItem('token');

  let previewType = '';
  if (this.isImage(file)) previewType = 'image';
  else if (this.isVideo(file)) previewType = 'video';
  else if (this.isAudio(file)) previewType = 'audio';
  else if (this.isPdf(file)) previewType = 'pdf';
  else if (this.isText(file)) previewType = 'text';

  const previewWindow = this.createWindow('preview', `预览: ${file.name}`, '👁️', {
    width: 900,
    height: 700,
    fileType: previewType,
    filePath: fullPath,
    fileName: file.name,
    isLoading: true,
    previewContent: '',
    previewError: ''
  });

  // [核心改动] 如果是PDF，调用 createPdfPreviewSession 方法
  if (this.isPdf(file)) {
    try {
      const sessionUrl = await this.createPdfPreviewSession(fullPath, token);
      previewWindow.previewContent = sessionUrl;
      previewWindow.isLoading = false;
    } catch (error) {
      previewWindow.previewError = 'PDF预览失败: ' + error.message;
      previewWindow.isLoading = false;
    }
    return;
  }
  if (this.isOffice(file)) {
    try {
      previewWindow.fileType = 'pdf';
      const convertUrl = `/api/office/convert-pdf?path=${encodeURIComponent(fullPath)}`;
      const response = await axios.get(convertUrl, { responseType: 'blob' });
      const pdfBlob = new Blob([response.data], { type: 'application/pdf' });
      previewWindow.previewContent = URL.createObjectURL(pdfBlob);
      previewWindow.isLoading = false;
    } catch (error) {
      previewWindow.previewError = 'Office 文件预览失败: ' + (error.response?.data?.error || error.message);
      previewWindow.isLoading = false;
    }
    return;
  }
  // 其他文件类型逻辑
  const url = `${axios.defaults.baseURL || ''}/api/download?path=${encodeURIComponent(fullPath)}&token=${encodeURIComponent(token)}`;
  if (this.isImage(file) || this.isVideo(file) || this.isAudio(file)) {
    previewWindow.previewContent = url;
    previewWindow.isLoading = false;
  } else if (this.isText(file)) {
    try {
      const response = await axios.get(url);
      previewWindow.previewContent = response.data;
      previewWindow.isLoading = false;
    } catch (err) {
      previewWindow.previewError = '文本加载异常: ' + (err.response?.data?.error || err.message);
      previewWindow.isLoading = false;
    }
  }
},


createPdfPreviewSession: async function(filePath, token) {
  try {
    const response = await axios.post('/api/create-preview-session', {
      file_path: filePath,
      file_type: 'pdf'
    });
    if (response.data.success && response.data.session_id) {
      const baseURL = axios.defaults.baseURL || ''; return `${baseURL}/api/preview-session/${response.data.session_id}`;
    } else {
      throw new Error(response.data.error || '创建预览会话失败');
    }
  } catch (error) {
    console.error('❌ 创建PDF预览会话失败:', error);
    const errorMsg = error.response?.data?.error || error.message;
    if (error.response?.status === 401) {
      throw new Error('登录已过期,请重新登录');
    }
    throw new Error('创建预览会话失败: ' + errorMsg);
  }
},
// 文件分享功能
async shareFile(window, file) {
  if (file.is_dir) {
    alert('暂不支持分享文件夹');
    return;
  }

  // 收藏夹/最近访问视图使用 file.path
const fullPath = (window.currentDrive === 'favorites' || window.currentDrive === 'recent')
  ? file.path
  : this.buildFullPath(window, file.name);

  // 显示分享对话框
  const password = prompt('设置分享密码(可选，直接确定则无密码):');
  const expireHours = prompt('有效期(小时):', '24');

  if (expireHours === null) return; // 用户取消

  try {
    const response = await fetch((axios.defaults.baseURL || '') + '/api/share', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_path: fullPath,
        password: password || '',
        expire_hours: parseInt(expireHours) || 24
      })
    });

    const data = await response.json();

    if (data.success) {
      // 显示分享链接 - ✅ 修改这里
      let shareUrl = data.full_url;
if (!shareUrl) {
  const proxyPrefix = axios.defaults.baseURL || '';
  shareUrl = location.origin + proxyPrefix + data.share_url;
}

      // 创建分享结果窗口
      const shareWindow = this.createWindow('share-result', '分享链接', '🔗', {
        width: 600,
        height: 400,
        shareUrl: shareUrl,
        password: password,
        fileName: file.name
      });

      // 复制到剪贴板
      navigator.clipboard.writeText(shareUrl).then(() => {
        console.log('分享链接已复制到剪贴板');
      }).catch(err => {
        console.error('复制失败:', err);
      });

    } else {
      alert('创建分享链接失败: ' + (data.error || '未知错误'));
    }
  } catch (error) {
    console.error('分享文件失败:', error);
    alert('分享失败: ' + error.message);
  }
},

// 预览选中的文件(工具栏按钮)
previewSelected(window) {
  if (window.selectedFiles.length !== 1) {
    alert('请选择一个文件进行预览');
    return;
  }

  const fileName = window.selectedFiles[0];
  const file = window.files.find(f => f.name === fileName);

  if (!file) {
    alert('文件不存在');
    return;
  }

  this.previewFile(window, file);
},

// 分享选中的文件(工具栏按钮)
shareSelected(window) {
  if (window.selectedFiles.length !== 1) {
    alert('请选择一个文件进行分享');
    return;
  }

  const fileName = window.selectedFiles[0];
  const file = window.files.find(f => f.name === fileName);

  if (!file) {
    alert('文件不存在');
    return;
  }

  this.shareFile(window, file);
},

// 执行健康检查
async performHealthCheck(window) {
    try {
        const response = await axios.get('/api/ec_health_check');
        window.healthReport = response.data;

        const total = response.data.total_files;
        const healthy = response.data.healthy_files;
        const atRisk = response.data.at_risk_files;
        const corrupted = response.data.corrupted_files;

        this.showToast(
            `✅ 检查完成: 总文件 ${total}，健康 ${healthy}，风险 ${atRisk}，损坏 ${corrupted}`,
            atRisk > 0 || corrupted > 0 ? 'warning' : 'success'
        );
    } catch (error) {
        this.showToast(`❌ 健康检查失败: ${error.response?.data?.error || error.message}`, 'error');
    }
},

// 批量恢复
async batchRecover(window) {
    if (!confirm('确认要批量修复所有可恢复的文件吗?此操作可能需要较长时间。')) {
        return;
    }

    try {
        this.showToast('🚀 正在批量修复文件...', 'info');

        const response = await axios.post('/api/ec_batch_recover', {
            auto_rebuild: true
        });

        const report = response.data.report;

        this.showToast(
            `✅ 修复完成: 成功 ${report.successfully_recovered}，失败 ${report.failed_recoveries.length}`,
            'success'
        );

        // 重新执行健康检查
        await this.performHealthCheck(window);

    } catch (error) {
        const errData = error.response?.data;

        if (errData?.need_disk_recovery) {
            const offlineDisks = errData.unavailable_disks || [];
            const replacedDisks = errData.replaced_disks || [];
            const emptyDisks = errData.empty_disks || [];  // 新增

            // 情况1：磁盘存在但没有数据（新硬盘占用了原盘符）
            if (emptyDisks.length > 0) {
                const diskInfo = emptyDisks[0];
                const confirmMsg =
                    `🟡 检测到新硬盘：\n\n` +
                    `盘符: ${diskInfo.disk}\n` +
                    `原因: ${diskInfo.reason}\n\n` +
                    `这可能是替换故障硬盘后插入的新硬盘。\n\n` +
                    `是否将数据重建到这个硬盘上？`;

                if (confirm(confirmMsg)) {
                    await this.rebuildOnReplacedDisk(diskInfo.disk);
                }
                return;
            }

            // 情况2：序列号检测到磁盘更换
            if (replacedDisks.length > 0) {
                const diskInfo = replacedDisks[0];
                const confirmMsg =
                    `🟡 检测到磁盘已更换：\n\n` +
                    `盘符: ${diskInfo.disk}\n` +
                    `原序列号: ${diskInfo.original_serial}\n` +
                    `新序列号: ${diskInfo.current_serial}\n\n` +
                    `是否将数据重建到这个新硬盘上？`;

                if (confirm(confirmMsg)) {
                    await this.rebuildOnReplacedDisk(diskInfo.disk);
                }
                return;
            }

            // 情况3：磁盘离线
            if (offlineDisks.length > 0) {
                let message = `🔴 以下磁盘离线：\n\n${offlineDisks.join(', ')}\n\n`;
                message += '请插入新硬盘后重试。';

                if (confirm(message)) {
                    this.openDiskRecoveryDialog(offlineDisks);
                }
                return;
            }
        } else {
            this.showToast(`❌ 批量修复失败: ${errData?.error || error.message}`, 'error');
        }
    }
},

// 打开磁盘恢复对话框
openDiskRecoveryDialog(problemDisks = []) {
    if (problemDisks.length === 0) {
        alert('没有需要恢复的磁盘');
        return;
    }

    const lostDisk = problemDisks[0];

    // 获取可用的新磁盘列表
    const configDisks = this.ecStatus.config_disks || [];
    const availableNewDisks = this.availableDrives
        .filter(d => {
            const drive = d.drive;
            const normDrive = drive.toUpperCase().replace(/\\/g, '/').replace(/\/$/, '');

            // 排除问题磁盘
            const isProblem = problemDisks.some(pd => {
                const normPd = pd.toUpperCase().replace(/\\/g, '/').replace(/\/$/, '');
                return normPd === normDrive;
            });
            if (isProblem) return false;

            // 排除已在配置中的正常磁盘
            const inConfig = configDisks.some(cd => {
                const normCd = cd.toUpperCase().replace(/\\/g, '/').replace(/\/$/, '');
                return normCd === normDrive;
            });
            if (inConfig) return false;

            return true;
        })
        .map(d => d.drive);

    if (availableNewDisks.length === 0) {
        alert('❌ 没有可用的新磁盘！\n\n请先插入新硬盘，然后重试。');
        return;
    }

    const diskOptions = availableNewDisks.map((d, i) => `${i + 1}. ${d}`).join('\n');
    const choice = prompt(
        `🔧 磁盘恢复\n\n` +
        `故障磁盘: ${lostDisk}\n\n` +
        `请选择新磁盘来替换（输入序号）:\n${diskOptions}`
    );

    if (!choice) return;

    const idx = parseInt(choice) - 1;
    if (idx < 0 || idx >= availableNewDisks.length) {
        alert('无效的选择');
        return;
    }

    const newDisk = availableNewDisks[idx];
    this.recoverDisk(lostDisk, newDisk);
},

// 执行磁盘恢复
async recoverDisk(lostDisk, newDisk) {
    if (!confirm(`确认要将数据从 ${lostDisk} 恢复到 ${newDisk} 吗？\n\n此操作会重建所有丢失的数据块。`)) {
        return;
    }

    try {
        this.showToast('🔄 正在恢复磁盘数据...', 'info');

        const response = await axios.post('/api/ec_recover', {
            lost_disk: lostDisk,
            new_disk: newDisk
        });

        if (response.data.success) {
            const msg = response.data.message || `磁盘恢复成功！已将数据迁移到 ${newDisk}`;
            this.showToast(`✅ ${msg}`, 'success');

            // 刷新数据
            await this.loadData();
            await this.fetchEcStatus();
        } else {
            this.showToast(`❌ 恢复失败: ${response.data.error}`, 'error');
        }
    } catch (error) {
        const errMsg = error.response?.data?.error || error.message;
        this.showToast(`❌ 磁盘恢复失败: ${errMsg}`, 'error');
        console.error('磁盘恢复错误:', error.response?.data || error);
    }
},


      // 在已更换的磁盘上重建数据
async rebuildOnReplacedDisk(disk) {
    try {
        this.showToast('🔄 正在重建数据到新硬盘...', 'info');

        const response = await axios.post('/api/ec_rebuild_replaced', {
            disk: disk
        });

        if (response.data.success) {
            this.showToast(`✅ ${response.data.message || '数据重建成功！'}`, 'success');
            await this.loadData();
            await this.fetchEcStatus();
        } else {
            this.showToast(`❌ 重建失败: ${response.data.error}`, 'error');
        }
    } catch (error) {
        const errMsg = error.response?.data?.error || error.message;
        this.showToast(`❌ 重建失败: ${errMsg}`, 'error');
    }
},
   async unlockDisk(drive, inFileManagerWindow = null) {
    const password = prompt(`请输入磁盘 [${drive}] 的解锁密码:`);
    if (!password) return;
    
    try {
        await axios.post('/api/encryption/unlock', { drive, password });
        this.showToast(`✅ 磁盘 ${drive} 解锁成功`, 'success');
        await this.fetchEncryptionStatus();
        
        // ✅ 刷新所有文件管理器窗口
        this.windows.forEach(w => {
            if (w.type === 'files') {
                // 更新侧边栏存储列表
                w.sidebar.storage = this.buildStorageList();
                
                // 如果当前窗口正在显示该磁盘,则自动刷新
                if (w.currentDrive === drive || 
                    (inFileManagerWindow && w.id === inFileManagerWindow.id)) {
                    this.loadFiles(w);
                }
            }
        });
    } catch (error) {
        this.showToast(`❌ 解锁失败: ${error.response?.data?.error || error.message}`, 'error');
    }
},



// [新增] 永久解密磁盘的方法
async decryptDiskPermanently(drive) {
    if (!confirm(`⚠️ 警告：永久解密磁盘\n\n您确定要永久解密磁盘 [${drive}] 吗？\n此操作会将所有文件还原为明文，且不可逆。`)) {
        return;
    }

    const password = prompt(`请输入磁盘 [${drive}] 的密码以开始解密:`);
    if (!password) {
        this.showToast('密码不能为空，操作已取消', 'info');
        return;
    }

    try {
        this.showToast(`🚀 已开始在后台解密磁盘 [${drive}]...`, 'info');
        const response = await axios.post('/api/encryption/decrypt-disk', {
            drive: drive,
            password: password
        });

        alert(response.data.message);

        setTimeout(() => {
            this.fetchEncryptionStatus();
        }, 3000);

    } catch (error) {
        this.showToast(`❌ 启动解密任务失败: ${error.response?.data?.error || error.message}`, 'error');
    }
},
    async lockDisk(drive) {
        if (!confirm(`确认要锁定磁盘 [${drive}] 吗？`)) return;
        try {
            await axios.post('/api/encryption/lock', { drive });
            this.showToast(`🔒 磁盘 ${drive} 已锁定`, 'info');
            await this.fetchEncryptionStatus();
            // 刷新文件管理器侧边栏
            this.windows.forEach(w => {
                if (w.type === 'files') {
                    w.sidebar.storage = this.buildStorageList();
                }
            });
        } catch (error) {
            this.showToast(`❌ 锁定失败: ${error.response?.data?.error || error.message}`, 'error');
        }
    },

    async openUserManagement() {
      const win = this.createWindow('users', '用户管理', '👥', {
        width: 900,
        height: 650,
        users: [],
        loading: true,
        editingUser: null,
        newPassword: '',
        refreshTimer: null
      });
      this.showStartMenu = false;
      await this.loadUsers(win);
      win.refreshTimer = setInterval(async () => {
        await this.loadUsers(win);
      }, 10000);
    },

   async loadUsers(window) {
  if (!this.user.is_admin) {
    this.showToast('⚠️ 需要管理员权限', 'error');
    return;
  }

  try {
    window.loading = true;  // ✅ 开始加载
    const response = await axios.get('/api/users');
    window.users = response.data || [];  // ✅ 确保至少是空数组
    console.log('[DEBUG] 用户列表加载成功:', window.users);  // 添加调试日志
  } catch (error) {
    console.error('加载用户列表失败:', error);
    window.users = [];  // ✅ 失败时设置为空数组
    this.showToast('❌ 加载用户列表失败: ' + (error.response?.data?.error || error.message), 'error');
  } finally {
    window.loading = false;  // ✅ 结束加载
  }
},

    async toggleUserActive(window, user) {
      if (!confirm(`确认${user.is_active ? '禁用' : '启用'}用户 ${user.username}?`)) {
        return;
      }

      try {
        await axios.patch(`/api/users/${user.id}`, {
          is_active: !user.is_active
        });
        this.showToast(`✅ 用户状态已更新`, 'success');
        await this.loadUsers(window);
      } catch (error) {
        this.showToast('❌ 操作失败: ' + (error.response?.data?.error || error.message), 'error');
      }
    },

    async toggleUserAdmin(window, user) {
      if (!confirm(`确认${user.is_admin ? '取消' : '授予'}用户 ${user.username} 的管理员权限?`)) {
        return;
      }

      try {
        await axios.patch(`/api/users/${user.id}`, {
          is_admin: !user.is_admin
        });
        this.showToast(`✅ 权限已更新`, 'success');
        await this.loadUsers(window);
      } catch (error) {
        this.showToast('❌ 操作失败: ' + (error.response?.data?.error || error.message), 'error');
      }
    },

    async resetUserPassword(window, user) {
      const newPassword = prompt(`为用户 ${user.username} 设置新密码:`);
      if (!newPassword || !newPassword.trim()) {
        return;
      }

      const confirmPassword = prompt('请再次输入新密码确认:');
      if (newPassword !== confirmPassword) {
        this.showToast('❌ 两次输入的密码不一致', 'error');
        return;
      }

      try {
        await axios.post('/api/admin/reset_password', {
          username: user.username,
          new_password: newPassword
        });
        this.showToast(`✅ 用户 ${user.username} 的密码已重置`, 'success');
      } catch (error) {
        this.showToast('❌ 重置密码失败: ' + (error.response?.data?.error || error.message), 'error');
      }
    },

    async setEncryptionPassword(drive, isConfigured) {
        const old_password = isConfigured ? prompt(`磁盘 [${drive}] 已有密码，请输入旧密码:`, '') : null;
        if (isConfigured && old_password === null) return;

        const new_password = prompt(`请输入磁盘 [${drive}] 的新密码:`);
        if (!new_password) {
            this.showToast('新密码不能为空', 'error');
            return;
        }
        const confirm_password = prompt('请再次输入新密码:');
        if (new_password !== confirm_password) {
            this.showToast('两次输入的密码不一致', 'error');
            return;
        }

        try {
            await axios.post('/api/encryption/set-password', {
                drives: [drive],
                old_password: old_password,
                new_password: new_password
            });
            this.showToast(`✅ 磁盘 ${drive} 密码设置成功`, 'success');
            await this.fetchEncryptionStatus();
        } catch (error) {
            this.showToast(`❌ 设置密码失败: ${error.response?.data?.error || error.message}`, 'error');
        }
    },
    // ==========================================
    // 系统窗口
    // ==========================================
    openSystemWindow() {
      const win = this.createWindow('system', '系统信息', '📊', {
        refreshTimer: null
      });
      win.refreshTimer = setInterval(async () => {
        await this.fetchSystemInfo();
      }, 5000);
      this.showStartMenu = false;
    },

      openDiskWindow() {
      const win = this.createWindow('disks', '磁盘管理', '💿', {
        activeTab: 'encryption',
        width: 900,
        height: 650,
        refreshTimer: null
      });
      // 启动自动刷新（每3秒）
      win.refreshTimer = setInterval(async () => {
        await this.fetchDiskInfo();
        await this.fetchEncryptionStatus();
        await this.fetchAvailableDrives();
        await this.fetchEcStatus();
      }, 3000);
      this.showStartMenu = false;
    },
    // ==================== 空间池状态 ====================
async fetchPoolStatus() {
  try {
    const res = await axios.get('/api/pool/status');
    this.poolStatus = res.data;
  } catch (e) {
    console.error('获取空间池状态失败:', e);
    this.poolStatus = { is_configured: false };
  }
},
// ==================== 池健康检查 ====================
async fetchPoolHealth() {
    try {
        const res = await axios.get('/api/pool/health');
        this.poolHealth = res.data;
        return res.data;
    } catch (e) {
        console.error('获取池健康状态失败:', e);
        this.poolHealth = null;
    }
},

// ==================== 获取可添加的磁盘 ====================
async fetchAvailableDisksForPool() {
    try {
        const res = await axios.get('/api/pool/available-disks');
        this.poolAvailableDisks = res.data;
    } catch (e) {
        console.error('获取可用磁盘失败:', e);
        this.poolAvailableDisks = [];
    }
},

// ==================== 打开添加磁盘对话框 ====================
async openAddDiskDialog() {
    await this.fetchAvailableDisksForPool();
    this.showAddDiskDialog = true;
},

closeAddDiskDialog() {
    this.showAddDiskDialog = false;
},

// ==================== 添加磁盘到池 ====================
async addDiskToPool(disk) {
    if (!confirm(`确定要将 ${disk} 添加到存储池吗？`)) return;

    try {
        const res = await axios.post('/api/pool/disk/add', { disk });
        this.showToast(`✅ ${res.data.message}`, 'success');
        this.showAddDiskDialog = false;
        await this.fetchPoolStatus();
        await this.fetchPoolHealth();
    } catch (e) {
        this.showToast(`❌ 添加失败: ${e.response?.data?.error || e.message}`, 'error');
    }
},

// ==================== 从池移除磁盘 ====================
async removeDiskFromPool(disk) {
    try {
        // 1. 先预检查
        const checkRes = await axios.post('/api/pool/disk/remove-check', { disk });
        const check = checkRes.data;

        // 2. 构建提示信息
        let msg = `确定要移除磁盘 ${disk} 吗？\n\n`;
        msg += `📁 该磁盘上有 ${check.file_count} 个文件\n`;
        msg += `💾 共占用 ${this.formatSize(check.used_bytes)}\n\n`;

        if (check.file_count === 0) {
            msg += `✅ 该磁盘上没有文件，可以安全移除。`;
        } else if (check.can_migrate) {
            msg += `✅ 其他磁盘剩余空间充足（${this.formatSize(check.other_free_bytes)}）\n`;
            msg += `文件将自动迁移到其他磁盘。`;
        } else {
            msg += `⚠️ 警告：其他磁盘空间不足！\n`;
            msg += `需要: ${this.formatSize(check.used_bytes)}\n`;
            msg += `可用: ${this.formatSize(check.other_free_bytes)}\n`;
            msg += `缺少: ${this.formatSize(check.shortage_bytes)}\n\n`;
            msg += `如继续移除，该磁盘上的 ${check.file_count} 个文件将丢失！`;
        }

        if (!confirm(msg)) return;

        // 3. 如果空间不足且有文件，二次确认
        let migrate = true;
        if (!check.can_migrate && check.file_count > 0) {
            if (!confirm('⚠️ 最后确认：空间不足，继续将导致数据丢失！\n\n确定要强制移除吗？')) {
                return;
            }
            migrate = false;  // 强制移除，不迁移
        }

        // 4. 显示进度
        this.encryptionProgress.show = true;
        this.encryptionProgress.status = 'running';
        this.encryptionProgress.title = migrate && check.file_count > 0
            ? `正在迁移 ${check.file_count} 个文件...`
            : '正在移除磁盘...';
        this.encryptionProgress.percent = 50;

        // 5. 执行移除
        const res = await axios.post('/api/pool/disk/remove', { disk, migrate });

        // 6. 显示结果
        let resultMsg = res.data.message || `已移除磁盘 ${disk}`;
        if (res.data.migrated_count > 0) {
            resultMsg = `✅ 已迁移 ${res.data.migrated_count} 个文件`;
        }
        if (res.data.failed_files?.length > 0) {
            resultMsg += `\n⚠️ ${res.data.failed_files.length} 个文件迁移失败`;
        }

        this.encryptionProgress.status = 'complete';
        this.encryptionProgress.title = resultMsg;
        this.encryptionProgress.percent = 100;

        await this.fetchPoolStatus();
        await this.fetchPoolHealth();

    } catch (e) {
        this.encryptionProgress.status = 'error';
        this.encryptionProgress.title = `❌ 操作失败: ${e.response?.data?.error || e.message}`;
    }

    setTimeout(() => { this.encryptionProgress.show = false; }, 3000);
},

// ==================== 预览重新平衡 ====================
async previewRebalance() {
    try {
        this.showToast('🔄 正在分析数据分布...', 'info');
        const res = await axios.post('/api/pool/rebalance', { dry_run: true });
        this.rebalancePreview = res.data;
        this.showRebalanceDialog = true;
    } catch (e) {
        this.showToast(`❌ 分析失败: ${e.response?.data?.error || e.message}`, 'error');
    }
},

closeRebalanceDialog() {
    this.showRebalanceDialog = false;
    this.rebalancePreview = null;
},

// ==================== 执行重新平衡 ====================
async executeRebalance() {
    if (!confirm('确定要执行数据重新平衡吗？\n\n这可能需要一些时间，请勿关闭页面。')) return;

    try {
        this.showToast('🔄 正在重新平衡数据...', 'info');
        const res = await axios.post('/api/pool/rebalance', { dry_run: false });

        this.showToast(`✅ 平衡完成！成功迁移 ${res.data.success_count || 0} 个文件`, 'success');
        this.showRebalanceDialog = false;
        this.rebalancePreview = null;
        await this.fetchPoolStatus();
        await this.fetchPoolHealth();
    } catch (e) {
        this.showToast(`❌ 平衡失败: ${e.response?.data?.error || e.message}`, 'error');
    }
},


// 执行搜索
async performSearch(window) {
    const keyword = window.searchKeyword?.trim();
    if (!keyword) {
        this.showToast('请输入搜索关键词', 'warning');
        return;
    }

    // 确定搜索路径
    let searchPath = '';
    if (window.currentDrive === 'favorites' || window.currentDrive === 'recent') {
        this.showToast('请先选择一个存储位置再搜索', 'warning');
        return;
    } else if (window.currentDrive === 'ec_volume') {
        searchPath = 'ec_volume';
    } else if (window.currentDrive.startsWith('pool://')) {
        searchPath = window.currentDrive;
    } else {
        // 物理磁盘 - 搜索当前目录
        searchPath = window.currentDrive + (window.currentPath || '').replace(/^\//, '');
    }

    window.isSearching = true;
    window.isSearchMode = true;

    try {
        const response = await axios.get('/api/search', {
            params: {
                keyword: keyword,
                path: searchPath,
                limit: 200
            }
        });

        if (response.data.success) {
            window.files = response.data.items || [];
            window.currentPath = `搜索: "${keyword}"`;
            window.searchResults = response.data.items || [];
            this.showToast(`找到 ${response.data.count} 个结果`, 'success');
        } else {
            this.showToast(response.data.error || '搜索失败', 'error');
        }
    } catch (e) {
        console.error('搜索失败:', e);
        this.showToast('搜索失败: ' + (e.response?.data?.error || e.message), 'error');
    } finally {
        window.isSearching = false;
    }
},

// 清除搜索，返回正常浏览模式
clearSearch(window) {
    window.searchKeyword = '';
    window.isSearchMode = false;
    window.searchResults = [];

    // 如果是全局搜索窗口（currentDrive === 'search'），直接关闭窗口
    if (window.currentDrive === 'search') {
        this.closeWindow(window.id);
        return;
    }

    // 否则返回正常浏览模式
    this.loadFiles(window);
},
// 从搜索结果中打开文件/文件夹
openSearchResult(window, file) {
    if (file.is_dir) {
        // 跳转到文件夹位置
        this.jumpToLocation(window, file.path);
    } else {
        // 预览文件，传入完整路径
        this.addToRecent(file, window);
        this.previewFile(window, file, file.path);
    }
    // 清除搜索模式
    window.isSearchMode = false;
    window.searchKeyword = '';
},
// ==================== 打开池配置对话框 ====================
openPoolWindow() {
  if (this.poolStatus.is_configured) {
    const win = this.createWindow('pool-detail', '空间池管理', '📦', {
      width: 800,
      height: 600,
      refreshTimer: null
    });
    win.refreshTimer = setInterval(async () => {
      await this.fetchPoolStatus();
      await this.fetchPoolHealth();
      await this.fetchPoolEncryptionStatus();
    }, 5000);
  } else {
    this.openPoolSetupDialog();
  }
},

openPoolSetupDialog() {
  // 筛选可用磁盘（排除已用于EC或加密的）
  this.poolSetupForm.availableDisks = this.availableDrives.filter(d => {
    // 排除纠删码磁盘
    if (this.ecStatus.is_configured && this.ecStatus.config_disks?.includes(d.drive)) {
      return false;
    }
    // 排除已加密磁盘
    const encStatus = this.encryptionStatus.find(s => s.drive === d.drive);
    if (encStatus && encStatus.is_configured) {
      return false;
    }
    return true;
  });

  this.poolSetupForm.selectedDisks = [];
  this.poolSetupForm.name = '主存储池';
  this.poolSetupForm.error = '';
  this.showPoolSetupDialog = true;
},

closePoolSetupDialog() {
  this.showPoolSetupDialog = false;
},

// ==================== 创建存储池 ====================
async submitPoolConfig() {
  const { name, selectedDisks } = this.poolSetupForm;
  this.poolSetupForm.error = '';

  if (selectedDisks.length < 1) {
    this.poolSetupForm.error = '请至少选择1个磁盘';
    return;
  }

  try {
    await axios.post('/api/pool/create', {
      name: name,
      disks: selectedDisks
    });

    this.showToast('✅ 存储池创建成功！', 'success');
    this.closePoolSetupDialog();
    await this.loadData();
  } catch (error) {
    const errorMsg = error.response?.data?.error || error.message;
    this.poolSetupForm.error = errorMsg;
    this.showToast(`❌ 创建失败: ${errorMsg}`, 'error');
  }
},

// ==================== 删除存储池 ====================


async removePool() {
  if (!this.user.is_admin) {
    this.showToast('❌ 需要管理员权限', 'error');
    return;
  }

  if (!confirm('⚠️ 警告：删除存储池\n\n此操作将：\n1. 删除存储池配置\n2. 释放所有参与的磁盘\n3. 逻辑卷数据将无法访问\n\n确定要继续吗？')) {
    return;
  }

  try {
    this.showToast('🚀 正在删除存储池...', 'info');

    const response = await axios.post('/api/pool/remove', { confirm: true });

    this.showToast(`✅ ${response.data.message || '存储池已删除'}`, 'success');

    await this.loadData();

    this.windows.forEach(w => {
      if (w.type === 'files') {
        w.sidebar.storage = this.buildStorageList();
      }
    });

  } catch (error) {
    this.showToast(`❌ 删除失败: ${error.response?.data?.error || error.message}`, 'error');
  }
},


// 获取池加密状态
async fetchPoolEncryptionStatus() {
    try {
        const res = await axios.get('/api/pool/encryption/status');
        this.poolEncryptionStatus = res.data;
    } catch (e) {
        this.poolEncryptionStatus = {};
    }
},


// 加密池或卷
async encryptTarget(type, name = 'main') {
    const label = type === 'pool' ? '存储池' : `逻辑卷 ${name}`;
    const password = prompt(`请设置${label}加密密码:`);
    if (!password) return;

    const confirm = prompt('请再次输入密码确认:');
    if (password !== confirm) {
        alert('两次密码不一致');
        return;
    }

    this.encryptionProgress.show = true;
    this.encryptionProgress.status = 'running';
    this.encryptionProgress.title = `正在加密${label}...`;
    this.encryptionProgress.percent = 0;

    try {
        const res = await axios.post('/api/pool/encrypt', { type, name, password });
        if (res.data.success) {
            this.encryptionProgress.status = 'complete';
            this.encryptionProgress.title = `✅ 加密完成，共处理 ${res.data.processed} 个文件`;
            this.encryptionProgress.percent = 100;
            await this.fetchPoolEncryptionStatus();
            // 刷新所有窗口的文件列表
this.windows.forEach(win => this.loadFiles(win));
        } else {
            throw new Error(res.data.error);
        }
    } catch (e) {
        this.encryptionProgress.status = 'error';
        this.encryptionProgress.title = `❌ 加密失败: ${e.response?.data?.error || e.message}`;
    }
    setTimeout(() => { this.encryptionProgress.show = false; }, 3000);
},

// 解密池或卷
async decryptTarget(type, name) {
    const label = type === 'pool' ? '存储池' : `逻辑卷 ${name}`;
    const password = prompt(`请输入${label}密码以永久解密:`);
    if (!password) return;
    if (!confirm(`确定要永久解密${label}吗？解密后数据将以明文存储。`)) return;

    this.encryptionProgress.show = true;
    this.encryptionProgress.status = 'running';
    this.encryptionProgress.title = `正在解密${label}...`;

    try {
        const res = await axios.post('/api/pool/decrypt', { type, name, password });
        if (res.data.success) {
            this.encryptionProgress.status = 'complete';
            this.encryptionProgress.title = `✅ 解密完成`;
            this.encryptionProgress.percent = 100;
            await this.fetchPoolEncryptionStatus();
        } else {
            throw new Error(res.data.error);
        }
    } catch (e) {
        this.encryptionProgress.status = 'error';
        this.encryptionProgress.title = `❌ 解密失败: ${e.response?.data?.error || e.message}`;
    }
    setTimeout(() => { this.encryptionProgress.show = false; }, 3000);
},

// 解锁池或卷
async unlockTarget(type, name) {
    const label = type === 'pool' ? '存储池' : `逻辑卷 ${name}`;
    const password = prompt(`请输入密码解锁${label}:`);
    if (!password) return;

    try {
        const res = await axios.post('/api/pool/unlock', { type, name, password });
        if (res.data.success) {
            alert(`✅ ${label}已解锁`);
            await this.fetchPoolEncryptionStatus();
        } else {
            alert('❌ 密码错误');
        }
    } catch (e) {
        alert('解锁失败: ' + (e.response?.data?.error || e.message));
    }
},

// 锁定池或卷
async lockTarget(type, name) {
    const label = type === 'pool' ? '存储池' : `逻辑卷 ${name}`;
    try {
        await axios.post('/api/pool/lock', { type, name });
        await this.fetchPoolEncryptionStatus();
        // 刷新所有窗口的文件列表
this.windows.forEach(win => this.loadFiles(win));
        alert(`🔒 ${label}已锁定`);
    } catch (e) {
        alert('锁定失败');
    }
},

// ==================== 逻辑卷管理 ====================
openVolumeDialog() {
  this.volumeForm = {
    name: '',
    display_name: '',
    icon: '📁',
    strategy: 'largest_free',
    error: ''
  };
  this.showVolumeDialog = true;
},

closeVolumeDialog() {
  this.showVolumeDialog = false;
},

async submitVolumeConfig() {
  const { name, display_name, icon, strategy } = this.volumeForm;
  this.volumeForm.error = '';

  if (!name || !display_name) {
    this.volumeForm.error = '请填写卷标识和显示名称';
    return;
  }

  // 验证卷标识格式
  if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(name)) {
    this.volumeForm.error = '卷标识必须以字母开头，只能包含字母、数字和下划线';
    return;
  }

  try {
    await axios.post('/api/pool/volume/create', {
      name,
      display_name,
      icon,
      strategy
    });

    this.showToast('✅ 逻辑卷创建成功！', 'success');
    this.closeVolumeDialog();
    await this.fetchPoolStatus();

    // 刷新文件管理器侧边栏
    this.windows.forEach(w => {
      if (w.type === 'files') {
        w.sidebar.storage = this.buildStorageList();
      }
    });
  } catch (error) {
    const errorMsg = error.response?.data?.error || error.message;
    this.volumeForm.error = errorMsg;
    this.showToast(`❌ 创建失败: ${errorMsg}`, 'error');
  }
},

async deleteVolume(volumeName) {
  if (!confirm(`确定要删除逻辑卷 "${volumeName}" 吗？\n\n该卷中的所有文件将被删除！`)) {
    return;
  }

  try {
    await axios.delete(`/api/pool/volume/${volumeName}?confirm=true`);
    this.showToast('✅ 逻辑卷已删除', 'success');
    await this.fetchPoolStatus();

    // 刷新文件管理器
    this.windows.forEach(w => {
      if (w.type === 'files') {
        w.sidebar.storage = this.buildStorageList();
      }
    });
  } catch (error) {
    this.showToast(`❌ 删除失败: ${error.response?.data?.error || error.message}`, 'error');
  }
},

// ==================== 打开池详情窗口 ====================
openPoolDetailWindow() {
  this.createWindow('pool-detail', '空间池管理', '📦', {
    width: 800,
    height: 600
  });
  this.showStartMenu = false;
},


 openUniverEditor(file, win) {
        // 构建完整路径
        const fullPath = this.buildFullPath(win, file.name);
        const token = localStorage.getItem('token');

        // ✅ 修复开始：获取动态的 BaseURL
        // 如果是通过管理端访问，这里会是 '/proxy/node/node-1'
        // 如果是直接访问，这里是 '' (空字符串)
        let baseUrl = axios.defaults.baseURL || '';

        // 防止出现双斜杠 (比如 /proxy/node/node-1//static)
        if (baseUrl.endsWith('/')) {
            baseUrl = baseUrl.slice(0, -1);
        }

      const editorUrl = `${baseUrl}/static/univer.html?path=${encodeURIComponent(fullPath)}&name=${encodeURIComponent(file.name)}&token=${encodeURIComponent(token)}&baseUrl=${encodeURIComponent(baseUrl)}&username=${encodeURIComponent(this.user.username)}&avatar=${encodeURIComponent(this.user.avatar || '')}`;
        console.log('[DEBUG] 打开 Univer URL:', editorUrl); // 方便你排查

        // 创建一个新窗口来承载 iframe
        const editorWindow = this.createWindow('univer-editor', `编辑: ${file.name}`, '📊', {
            width: 1200,
            height: 800,
            url: editorUrl
        });

        this.showStartMenu = false;
    },
// ==================== 重建索引 ====================
async rebuildPoolIndex() {
  if (!confirm('确定要重建文件索引吗？\n\n这将扫描所有物理文件并重建索引数据库。')) {
    return;
  }

  try {
    this.showToast('🔄 正在重建索引...', 'info');
    const res = await axios.post('/api/pool/rebuild');
    this.showToast(`✅ ${res.data.message}`, 'success');
    await this.fetchPoolStatus();
  } catch (error) {
    this.showToast(`❌ 重建失败: ${error.response?.data?.error || error.message}`, 'error');
  }
},



openECConfig() {
  // 不再重新打开窗口，而是调用新的方法打开配置对话框
  this.openEcSetupDialog();
},
    // 建议将这些新方法放在 openECConfig() 方法的后面

// [新增] 打开EC配置对话框
openEcSetupDialog() {
  // 重置表单为默认值
  this.ecSetupForm = {
    k: 4,
    m: 2,
    selectedDisks: [],
    capacityEstimate: null,
    error: ''
  };
  // 从可用磁盘中筛选出未参与EC且未加密的磁盘作为选项
  this.ecSetupForm.availableDisks = this.availableDrives.filter(d => {
    const encStatus = this.encryptionStatus.find(s => s.drive === d.drive);
    return !this.ecStatus.config_disks?.includes(d.drive) && !(encStatus && encStatus.is_configured);
  });
  this.showEcSetupDialog = true;
},

// [新增] 关闭EC配置对话框
closeEcSetupDialog() {
  this.showEcSetupDialog = false;
},

// [新增] 提交EC配置
async submitEcConfig() {
  const { k, m, selectedDisks } = this.ecSetupForm;
  this.ecSetupForm.error = '';

  if (selectedDisks.length < k + m) {
    this.ecSetupForm.error = `磁盘数量不足，需要 ${k + m} 个，当前选中 ${selectedDisks.length} 个。`;
    return;
  }

  try {
    await axios.post('/api/ec_config', {
      scheme: 'rs',
      k: k,
      m: m,
      disks: selectedDisks
    });
    this.showToast('✅ 纠删码配置成功！', 'success');
    this.closeEcSetupDialog();
    // 重新加载数据以更新桌面状态
    await this.loadData();
  } catch (error) {
    const errorMsg = error.response?.data?.error || error.message;
    this.ecSetupForm.error = `配置失败: ${errorMsg}`;
    this.showToast(`❌ 配置失败: ${errorMsg}`, 'error');
  }
},

    // 硬盘恢复：替换丢失的硬盘
async recoverLostDisk() {
  if (!this.ecStatus.lost_disks || this.ecStatus.lost_disks.length === 0) {
    this.showToast('❌ 没有检测到丢失的硬盘', 'error');
    return;
  }

  const lostDisk = this.ecStatus.lost_disks[0]; // 取第一个丢失的硬盘

  // 显示可用的新硬盘列表
  const availableDisks = this.ecStatus.available_new_disks || [];
  if (availableDisks.length === 0) {
    this.showToast('❌ 没有可用的新硬盘来替换', 'error');
    return;
  }

  const diskOptions = availableDisks.map((d, i) => `${i + 1}. ${d}`).join('\n');
  const selection = prompt(
    `检测到丢失的硬盘: ${lostDisk}\n\n请选择用于替换的新硬盘（输入序号）:\n${diskOptions}`
  );

  if (!selection) return;

  const index = parseInt(selection) - 1;
  if (index < 0 || index >= availableDisks.length) {
    this.showToast('❌ 无效的选择', 'error');
    return;
  }

  const newDisk = availableDisks[index];

  if (!confirm(`确认用 ${newDisk} 替换丢失的硬盘 ${lostDisk}?\n\n此操作将重建所有丢失的数据分片，可能需要较长时间。`)) {
    return;
  }

  try {
    this.showToast('🚀 正在恢复硬盘数据...', 'info');

    const response = await axios.post('/api/ec_recover', {
      lost_disk: lostDisk,
      new_disk: newDisk
    });

    this.showToast(`✅ ${response.data.message}`, 'success');

    // 刷新状态
    await this.loadData();
  } catch (error) {
    this.showToast(`❌ 恢复失败: ${error.response?.data?.error || error.message}`, 'error');
  }
},

   startEncryption(drive) {
  this.encryptionProgress.show = true;
  this.encryptionProgress.status = 'running';
  this.encryptionProgress.title = `正在加密 ${drive}...`;
  this.encryptionProgress.percent = 0;

  const interval = setInterval(() => {
    if (this.encryptionProgress.percent < 100)
      this.encryptionProgress.percent += 5;
  }, 500);

  axios.post('/api/encryption/disk/encrypt', { drive })
    .then(res => {
      this.encryptionProgress.status = 'complete';
      this.encryptionProgress.percent = 100;
      this.encryptionProgress.title = '加密完成 ✅';
    })
    .catch(() => {
      this.encryptionProgress.status = 'error';
      this.encryptionProgress.title = '加密失败 ❌';
    })
    .finally(() => {
      setTimeout(() => {
        clearInterval(interval);
        this.encryptionProgress.show = false;
      }, 3000);
    });
},

openECDetailConfig() {
  // 不再是 alert，而是创建一个新类型的窗口
  const window = this.createWindow('ec-detail', '纠删码详细配置', '🛡️', {
    width: 700,
    height: 550,
    // 将当前的 ecStatus 数据传递给新窗口
    ecDetails: { ...this.ecStatus }
  });
  this.showStartMenu = false;
},


    // 取消纠删码配置
async removeEcConfig() {
  if (!this.user.is_admin) {
    this.showToast('❌ 需要管理员权限', 'error');
    return;
  }

  if (!confirm('⚠️ 警告：删除纠删码配置\n\n此操作将：\n1. 删除所有纠删码文件（无法恢复）\n2. 清除纠删码配置\n3. 释放参与纠删码的磁盘\n\n确定要继续吗？')) {
    return;
  }

  try {
    this.showToast('🚀 正在删除纠删码配置...', 'info');

    const response = await axios.post('/api/ec_remove', { confirm: true });

    this.showToast(`✅ ${response.data.message}`, 'success');

    await this.loadData();

    this.windows.forEach(w => {
      if (w.type === 'files') {
        w.sidebar.storage = this.buildStorageList();
      }
    });

  } catch (error) {
    this.showToast(`❌ 删除失败: ${error.response?.data?.error || error.message}`, 'error');
  }
},


    // 批量导出纠删码文件
async exportAllEcFiles() {
  if (!this.user.is_admin) {
    this.showToast('❌ 需要管理员权限', 'error');
    return;
  }

  if (!this.ecStatus.is_configured) {
    this.showToast('❌ 未配置纠删码', 'error');
    return;
  }

  // 获取可用的物理磁盘列表（排除EC卷）
  const availableDisks = this.availableDrives.map(d => d.drive);

  if (availableDisks.length === 0) {
    this.showToast('❌ 没有可用的物理磁盘', 'error');
    return;
  }

  // 显示磁盘选择对话框
  const diskOptions = availableDisks.map((d, i) => `${i + 1}. ${d}`).join('\n');
  const selection = prompt(
    `批量导出纠删码文件\n\n` +
    `所有文件将被解码并导出到指定磁盘的 ec_export 目录\n\n` +
    `请选择目标磁盘（输入序号）:\n${diskOptions}`
  );

  if (!selection) return;

  const index = parseInt(selection) - 1;
  if (index < 0 || index >= availableDisks.length) {
    this.showToast('❌ 无效的选择', 'error');
    return;
  }

  const targetDisk = availableDisks[index];

  if (!confirm(
    `确认导出所有纠删码文件到 ${targetDisk}?\n\n` +
    `文件将保存到: ${targetDisk}ec_export/[时间戳]/\n` +
    `此操作可能需要较长时间，请耐心等待。`
  )) {
    return;
  }

  try {
    this.showToast('🚀 正在导出文件，请稍候...', 'info');

    const response = await axios.post('/api/ec_export_all', {
      target_disk: targetDisk
    });

    const data = response.data;

    // 显示详细结果
    let message = `✅ 导出完成！\n\n`;
    message += `总文件数: ${data.total_files}\n`;
    message += `成功导出: ${data.exported_count}\n`;
    message += `失败文件: ${data.failed_count}\n\n`;
    message += `导出目录:\n${data.export_path}\n\n`;

    if (data.failed_count > 0) {
      message += `失败详情请查看导出目录中的 _export_report.txt 文件`;
    }

    alert(message);
    this.showToast(data.message, data.failed_count > 0 ? 'warning' : 'success');

  } catch (error) {
    this.showToast(`❌ 导出失败: ${error.response?.data?.error || error.message}`, 'error');
  }
},

async checkCurrentUser() {
  // 1. 检查 URL 中是否有 token 参数
  const urlParams = new URLSearchParams(window.location.search);
  const accessToken = urlParams.get('token');

  if (accessToken) {
    // ✅ 访问令牌登录流程
    try {
      const res = await axios.post('/api/verify-access-token', {
        token: accessToken
      });

     if (res.data.success && res.data.user && res.data.token) {
    this.user = {
        ...res.data.user,
        avatar: res.data.user.avatar || ''  // 确保头像字段存在
    };
    this.loggedIn = true;

    // 保存新的长期 token
    localStorage.setItem('token', res.data.token);
    localStorage.setItem('user', JSON.stringify(this.user));
    localStorage.setItem('userAvatar', res.data.user.avatar || '');  // 单独保存头像
    axios.defaults.headers.common['Authorization'] = 'Bearer ' + res.data.token;

        // ✅ 清除 URL 中的 token(安全!)
        window.history.replaceState({}, document.title, '/desktop');

        await this.loadData();
        this.showToast(`✅ 欢迎回来, ${this.user.username}`, 'success');
        return;
      }
    } catch (err) {
      console.error('Token 验证失败:', err);
      this.showToast('❌ 访问令牌无效或已过期,请重新登录', 'error');
      // 清除本地认证信息
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      // ✅ 跳转回管理端登录页,带上 redirect=client 参数
      setTimeout(async () => {
        try {
          const nodeInfo = await axios.get('/api/node-info').then(res => res.data);
          window.location.href = `${nodeInfo.center_url}/login.html?redirect=client&node_id=${nodeInfo.node_id}`;
        } catch (err) {
          console.error('获取节点信息失败:', err);
          window.location.href = 'http://127.0.0.1:8080/login.html?redirect=client';
        }
      }, 2000);
      return;
    }
  }

  // 2. 检查本地是否有 token
  const localToken = localStorage.getItem('token');
  if (localToken) {
    try {
      axios.defaults.headers.common['Authorization'] = 'Bearer ' + localToken;
      const res = await axios.get('/api/current-user');

      if (res.data.user) {
    this.user = {
        ...res.data.user,
        avatar: res.data.user.avatar || localStorage.getItem('userAvatar') || ''
    };
    this.loggedIn = true;
    await this.loadData();
    return;
}
    } catch (err) {
      // token 过期,清除
      localStorage.removeItem('token');
      localStorage.removeItem('user');
    }
  }

  // 3. 都没有,跳转回管理端登录页
  this.showToast('❌ 未登录,请先登录', 'warning');
  setTimeout(async () => {
    try {
      const nodeInfo = await axios.get('/api/node-info').then(res => res.data);
      window.location.href = `${nodeInfo.center_url}/login.html?redirect=client&node_id=${nodeInfo.node_id}`;
    } catch (err) {
      console.error('获取节点信息失败:', err);
      window.location.href = 'http://127.0.0.1:8080/login.html?redirect=client';
    }
  }, 1000);
},
    openEncryptionConfig() {
      alert('打开磁盘加密配置\n(跳转到传统配置界面)');
    },


    toggleStartMenu() {
      this.showStartMenu = !this.showStartMenu;
    },

    updateTime() {
      const now = new Date();
      this.currentTime = now.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
      });
    },


    formatSize(bytes) {
      if (!bytes) return '-';
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let size = bytes;
      let unitIndex = 0;
      while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
      }
      return size.toFixed(1) + ' ' + units[unitIndex];
    },

    formatTime(timestamp) {
      if (!timestamp) return '-';
      const date = new Date(timestamp * 1000);
      return date.toLocaleString('zh-CN');
    },

    getFileIcon(filename) {
      if (!filename) return '📄';

      // ✅ 1. 加密文件显示锁图标 (保持原逻辑)
      if (filename.endsWith('.encrypted')) {
        return '🔒';
      }

      const ext = filename.split('.').pop().toLowerCase();

      // ✅ 2. 扩展图标库映射
      const icons = {
        // Office - Word (蓝色)
        docx: '📘', doc: '📘', odt: '📘',

        // Office - Excel (图表/绿色系)
        xlsx: '📊', xls: '📊', csv: '📈', ods: '📊',

        // Office - PPT (投影仪/橙色系)
        pptx: '📽️', ppt: '📽️', odp: '📽️',

        // PDF (红色)
        pdf: '📕',

        // 图片
        jpg: '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️',
        bmp: '🖼️', webp: '🖼️', svg: '🎨', ico: '🎨',

        // 视频
        mp4: '🎬', mkv: '🎬', avi: '🎬', mov: '🎬',
        wmv: '🎬', flv: '🎬', webm: '🎬',

        // 音频
        mp3: '🎵', wav: '🎵', flac: '🎵', m4a: '🎵',
        wma: '🎵', ogg: '🎵', aac: '🎵',

        // 压缩包
        zip: '📦', rar: '📦', '7z': '📦', tar: '📦',
        gz: '📦', xz: '📦', iso: '💿',

        // 代码/文本
        txt: '📝', md: '📝', log: '📝',
        html: '🌐', htm: '🌐',
        js: '📜', ts: '📜', json: '⚙️', css: '🎨',
        py: '🐍', java: '☕', c: '💻', cpp: '💻',

        // 系统/执行
        exe: '🚀', sh: '💻', bat: '💻'
      };

      return icons[ext] || '📄';
    },


    copyToClipboard(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
          this.showToast('✅ 已复制到剪贴板', 'success');
        }).catch(err => {
          console.error('复制失败:', err);
          this.fallbackCopyToClipboard(text);
        });
      } else {
        this.fallbackCopyToClipboard(text);
      }
    },  // ⚠️ 注意这里有逗号!

    // 备用复制方法(兼容旧浏览器)
    fallbackCopyToClipboard(text) {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      document.body.appendChild(textArea);
      textArea.select();

      try {
        document.execCommand('copy');
        this.showToast('✅ 已复制到剪贴板', 'success');
      } catch (err) {
        console.error('复制失败:', err);
        this.showToast('❌ 复制失败,请手动复制', 'error');
      }

      document.body.removeChild(textArea);
    },  // ⚠️ 注意这里有逗号!

    // 显示Toast提示消息
    showToast(message, type = 'info') { //
      // ... (您的 showToast 代码) ...
        const toast = document.createElement('div');
        toast.textContent = message;
        toast.className = `fixed top-5 left-1/2 transform -translate-x-1/2 text-white px-6 py-3 rounded-lg shadow-lg z-[2000] opacity-0 transition-all duration-300`;

        // 根据类型设置颜色
        if (type === 'success') {
            toast.classList.add('bg-green-500');
        } else if (type === 'error') {
            toast.classList.add('bg-red-500');
        } else {
            toast.classList.add('bg-blue-500');
        }

        document.body.appendChild(toast);

        // 动画效果
        setTimeout(() => {
            toast.style.opacity = '1'; // 先显示
            toast.style.transform = 'translate(-50%, 0)';
        }, 50); // 短暂延迟确保元素已渲染

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translate(-50%, -20px)';
        }, 2000); // 2秒后开始消失

        setTimeout(() => {
            if (document.body.contains(toast)) { // 检查元素是否还在
                document.body.removeChild(toast);
            }
        }, 2500); // 2.5秒后移除DOM
    }
},

  computed: {
      // 搜索匹配的应用
matchedApps() {
  if (!this.searchQuery.trim()) return [];
  const query = this.searchQuery.trim().toLowerCase();
  return this.appList.filter(app => {
    if (app.adminOnly && !this.user.is_admin) return false;
    return app.name.toLowerCase().includes(query) ||
           app.keywords.some(kw => kw.toLowerCase().includes(query));
  });
},
  canRead() {
    const permission = this.user.file_permission;
    return permission === 'readonly' ||
           permission === 'readwrite' ||
           permission === 'fullcontrol';
  },

  canWrite() {
    const permission = this.user.file_permission;
    return permission === 'readwrite' ||
           permission === 'fullcontrol';
  },

  canDelete() {
    return this.user.file_permission === 'fullcontrol';
  },

  canUpload() {
    return this.canWrite;
  },

  standaloneDiskEncryption() {
        if (!this.encryptionStatus || !Array.isArray(this.encryptionStatus)) {
            return [];
        }

        // 获取池中的磁盘列表
        const poolDisks = (this.poolStatus.disks || []).map(d => {
            // 统一格式：大写 + 反斜杠
            const disk = typeof d === 'string' ? d : d.disk;
            return disk?.toUpperCase().replace(/\//g, '\\');
        });

        // 过滤掉池内磁盘
        return this.encryptionStatus.filter(disk => {
            const normalizedDrive = disk.drive?.toUpperCase().replace(/\//g, '\\');
            return !poolDisks.includes(normalizedDrive);
        });
    }
},

  mounted() {
  this.updateTime();
  setInterval(this.updateTime, 1000);

  document.addEventListener('contextmenu', (e) => {
    if (this.loggedIn) {
      e.preventDefault();
    }
  });

  document.addEventListener('click', () => {
    if (this.contextMenu.show) {
      this.closeContextMenu();
    }
    if (this.showStartMenu) {
      this.showStartMenu = false;
    }
  });
  const currentPath = window.location.pathname;
  if (currentPath.includes('/proxy/node/')) {
    const match = currentPath.match(/^(\/proxy\/node\/[^\/]+)/);
    if (match) {
      axios.defaults.baseURL = match[1];
      console.log('[DEBUG] 设置axios baseURL:', match[1]);
    }
  }
  // ✅ 改为调用新的检查用户方法
  this.checkCurrentUser();



},
updated() {

}
}).mount('#app');