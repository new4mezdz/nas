const { createApp } = Vue;

createApp({
  data() {
    return {
      // ========== 用户认证 ==========
      loggedIn: false,
      user: { username: '', is_admin: false },
      showRegister: false,
      loginForm: { username: '', password: '' },
      registerForm: { username: '', password: '', confirm: '' },
      errorMessage: '',
      infoMessage: '',

      // ========== 桌面系统 ==========
      windows: [],
      nextWindowId: 1,
      maxZIndex: 100,
      dragging: null,

      // ========== 任务栏 ==========
      showStartMenu: false,
      currentTime: '',

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

      // ========== 文件上传 ==========
      showUploadDialog: false,
      uploadFiles: [],
      dragOver: false,
      uploadStatus: '',
      currentUploadWindow: null
    };
  },

  methods: {
    // ==========================================
    // 登录认证
    // ==========================================
    async login() {
      this.errorMessage = '';
      if (!this.loginForm.username || !this.loginForm.password) {
        this.errorMessage = '请输入用户名和密码';
        return;
      }
      try {
        const res = await axios.post('/api/login', {
          username: this.loginForm.username,
          password: this.loginForm.password
        });
        localStorage.setItem('token', res.data.token);
        localStorage.setItem('user', JSON.stringify(res.data.user));
        axios.defaults.headers.common['Authorization'] = 'Bearer ' + res.data.token;
        this.user = res.data.user;
        this.loggedIn = true;
        this.loginForm.password = '';
        await this.loadData();
      } catch (err) {
        this.errorMessage = err.response?.data?.error || '登录失败';
      }
    },

    async register() {
      this.errorMessage = '';
      if (!this.registerForm.username || !this.registerForm.password) {
        this.errorMessage = '请输入用户名和密码';
        return;
      }
      if (this.registerForm.password !== this.registerForm.confirm) {
        this.errorMessage = '两次密码输入不一致';
        return;
      }
      try {
        await axios.post('/api/register', {
          username: this.registerForm.username,
          password: this.registerForm.password
        });
        this.infoMessage = '注册成功,请登录';
        this.loginForm.username = this.registerForm.username;
        this.loginForm.password = this.registerForm.password;
        this.showRegister = false;
      } catch (err) {
        this.errorMessage = err.response?.data?.error || '注册失败';
      }
    },

    logout() {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      this.loggedIn = false;
      this.user = { username: '', is_admin: false };
      this.windows = [];
      this.showStartMenu = false;
      delete axios.defaults.headers.common['Authorization'];
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
          this.fetchEncryptionStatus()
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
        if (!this.user.is_admin) return; // 仅管理员可获取
        try {
            const res = await axios.get('/api/encryption/status');
            this.encryptionStatus = res.data;
        } catch (e) {
            console.error('获取加密状态失败:', e);
            this.showToast('❌ 获取加密状态失败', 'error');
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
        const res = await axios.get('/api/ec_status');
        this.ecStatus = res.data;
      } catch (e) {
        console.error('获取纠删码状态失败:', e);
      }
    },

    // ==========================================
    // 窗口管理
    // ==========================================
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

// 提交密码修改
async submitPasswordChange(window) {
  const form = window.passwordForm;

  if (!form.oldPassword || !form.newPassword || !form.confirmPassword) {
    this.showToast('⚠️ 请填写完整信息', 'warning');
    return;
  }

  if (form.newPassword !== form.confirmPassword) {
    this.showToast('❌ 两次输入的密码不一致', 'error');
    return;
  }

  if (form.newPassword.length < 6) {
    this.showToast('⚠️ 密码长度至少 6 位', 'warning');
    return;
  }

  try {
    await axios.patch('/api/change_password', {
      old_password: form.oldPassword,
      new_password: form.newPassword
    });
    this.showToast('✅ 密码修改成功', 'success');

    // 清空表单
    form.oldPassword = '';
    form.newPassword = '';
    form.confirmPassword = '';
  } catch (error) {
    this.showToast(`❌ 修改失败: ${error.response?.data?.error || error.message}`, 'error');
  }
},

    closeWindow(id) {
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
        searching: false,
        sortBy: 'name',
        sortOrder: 'asc'
      });

      this.loadFiles(window);
      return window;
    },

    buildStorageList() {
  const storage = [];

  // 添加物理磁盘
  this.availableDrives.forEach(drive => {
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

  return storage;
},

    // 在 desktop.app.js 的 methods 中添加

// 打开个人设置
openPersonalSettings() {
  const window = this.createWindow('settings', '个人设置', '⚙️', {
    width: 600,
    height: 500,
    currentTab: 'profile' // profile, password
  });
  this.showStartMenu = false;
},

// 修改个人密码
async changePassword(window) {
  const oldPassword = prompt('请输入当前密码:');
  if (!oldPassword) return;

  const newPassword = prompt('请输入新密码:');
  if (!newPassword) return;

  const confirmPassword = prompt('请再次输入新密码:');
  if (newPassword !== confirmPassword) {
    this.showToast('❌ 两次输入的密码不一致', 'error');
    return;
  }

  try {
    await axios.patch('/api/change_password', {
      old_password: oldPassword,
      new_password: newPassword
    });
    this.showToast('✅ 密码修改成功', 'success');
  } catch (error) {
    this.showToast(`❌ 修改失败: ${error.response?.data?.error || error.message}`, 'error');
  }
},

    async loadFiles(window) {
  window.isLocked = false; // 每次加载前重置状态
  const token = localStorage.getItem('token');
  if (!token) {
    this.showToast('未登录', 'error');
    return;
  }

  let fullPath;
  if (window.currentDrive === 'ec_volume') {
    fullPath = window.currentPath.startsWith('ec_volume') ? window.currentPath : 'ec_volume';
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
    if (errorType === 'disk_locked') {
      window.isLocked = true;
      window.files = [];
      const drive = errorData.drive;

      this.showToast(`🔒 ${errorMsg}`, 'warning');

      // 自动弹出解锁对话框
      setTimeout(async () => {
        const shouldUnlock = confirm(`磁盘 ${drive} 已锁定\n\n是否立即解锁?`);
        if (shouldUnlock) {
          await this.unlockDisk(drive, window);
        }
      }, 100);
    } else {
      this.showToast(`❌ 加载失败: ${errorMsg}`, 'error');
    }
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
      if (file.is_dir) {
        this.openFolder(window, file.name);
      } else {
        this.previewFile(window, file);
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
      } else {
        let cleanPath = window.currentPath.replace(/^\//, '');
        if (cleanPath === '' || cleanPath === '/') {
          return window.currentDrive + fileName;
        }
        return window.currentDrive + cleanPath + '/' + fileName;
      }
    },

    downloadFile(win, file) { // <--- 修改这里
  const fullPath = this.buildFullPath(win, file.name); // <--- 修改这里
  const token = localStorage.getItem('token');
  const url = `/api/download?path=${encodeURIComponent(fullPath)}&token=${encodeURIComponent(token)}`;
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

    // 重命名选中项(工具栏按钮)
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

  // 调用重命名方法(会弹出输入框)
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

      let successCount = 0;
      let failCount = 0;

      for (const fileName of window.selectedFiles) {
        try {
          const fullPath = this.buildFullPath(window, fileName);
          const response = await fetch('/api/delete', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${localStorage.getItem('token')}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ path: fullPath })
          });

          const data = await response.json();
          if (data.success) {
            successCount++;
          } else {
            failCount++;
          }
        } catch (error) {
          failCount++;
        }
      }

      if (successCount > 0) {
        this.loadFiles(window);
        window.selectedFiles = [];
      }

      if (failCount > 0) {
        alert(`删除完成: 成功 ${successCount} 项, 失败 ${failCount} 项`);
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

    openUploadDialog(window) {
      this.showUploadDialog = true;
      this.uploadFiles = [];
      this.uploadStatus = '';
      this.currentUploadWindow = window;
    },
// 重命名文件/文件夹
async renameFile(window, file, newName) {
  // 如果没有提供新名称,弹出输入框
  if (!newName) {
    const oldName = typeof file === 'string' ? file : file.name;
    newName = prompt('请输入新名称:', oldName);
  }

  if (!newName || !newName.trim()) {
    return;
  }

  const oldName = typeof file === 'string' ? file : file.name;

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
async createNewFolder(window) {
  const folderName = prompt('请输入新文件夹名称:', '新建文件夹');

  if (!folderName || !folderName.trim()) {
    return;
  }

  // 检查文件名是否包含非法字符
  if (/[<>:"/\\|?*]/.test(folderName)) {
    this.showToast('❌ 文件夹名包含非法字符', 'error');
    return;
  }

  try {
    let parentPath;

    // 构建父路径
    if (window.currentDrive === 'ec_volume') {
      parentPath = window.currentPath.startsWith('ec_volume')
        ? window.currentPath
        : 'ec_volume';
    } else {
      const cleanPath = window.currentPath.replace(/^\//, '');
      parentPath = cleanPath ? window.currentDrive + cleanPath : window.currentDrive;
    }

    // 发送创建请求
    const response = await axios.post('/api/mkdir', {
      parent: parentPath,
      name: folderName
    });

    if (response.data.success) {
      this.showToast(`✅ 文件夹 "${folderName}" 创建成功`, 'success');
      // 刷新文件列表
      this.loadFiles(window);
    } else {
      this.showToast(`❌ 创建失败: ${response.data.error}`, 'error');
    }
  } catch (error) {
    console.error('创建文件夹失败:', error);
    const errorMsg = error.response?.data?.error || error.message;
    this.showToast(`❌ 创建失败: ${errorMsg}`, 'error');
  }
},


    // ==========================================
// 文件/文件夹加密功能
// ==========================================

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
      } else {
        const cleanPath = window.currentPath.replace(/^\//, '');
        uploadPath = cleanPath ? window.currentDrive + cleanPath : window.currentDrive;
      }

      uploadPath = uploadPath.replace(/\\/g, '/').replace(/\/{2,}/g, '/');

      const token = localStorage.getItem('token');

      for (const file of this.uploadFiles) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('path', uploadPath);

        try {
          const res = await fetch('/api/upload', {
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

    // ==========================================
    // 右键菜单
    // ==========================================
    showFileContextMenu(event, file, window) {
  event.preventDefault();

  // 判断文件是否已加密
  const isEncrypted = file.name.endsWith('.encrypted');

  this.contextMenu = {
    show: true,
    x: event.clientX,
    y: event.clientY,
    items: [
      {
        icon: file.is_dir ? '📂' : '👁️',
        label: file.is_dir ? '打开' : '预览',
        action: () => {
          if (file.is_dir) {
            this.handleDoubleClick(window, file);
          } else {
            this.previewFile(window, file);
          }
        },
        disabled: isEncrypted  // 加密文件禁用预览
      },
      {
        icon: '📥',
        label: '下载',
        action: () => this.downloadFile(window, file),
        disabled: file.is_dir || isEncrypted  // 加密文件禁用下载
      },
      {
        icon: '🔗',
        label: '分享',
        action: () => this.shareFile(window, file),
        disabled: file.is_dir || isEncrypted  // 加密文件禁用分享
      },
      { separator: true },

      // ✅ 新增：加密/解密选项
      {
        icon: isEncrypted ? '🔓' : '🔒',
        label: isEncrypted ? '解密' : '加密',
        action: () => {
          if (isEncrypted) {
            this.decryptFileOrFolder(window, file);
          } else {
            this.encryptFileOrFolder(window, file);
          }
        }
      },

      { separator: true },
      { icon: '✂️', label: '剪切', action: () => this.cutFile(window, file) },
      { icon: '📋', label: '复制', action: () => this.copyFile(window, file) },
      { separator: true },
      { icon: '✏️', label: '重命名', action: () => this.renameFile(window, file) },
      { icon: '🗑️', label: '删除', action: () => this.deleteFile(window, file) }
    ]
  };
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
        alert('剪贴板为空');
        return;
      }

      const mode = window.clipboard.mode;
      const count = window.clipboard.items.length;

      alert(`粘贴功能开发中...\n将${mode === 'cut' ? '移动' : '复制'} ${count} 项到当前位置`);

      // TODO: 实现实际的粘贴逻辑
      this.closeContextMenu();
    },



    async deleteFile(window, file) {
      if (!confirm(`确认删除 ${file.name}?`)) {
        this.closeContextMenu();
        return;
      }

      try {
        const fullPath = this.buildFullPath(window, file.name);
        const response = await fetch('/api/delete', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ path: fullPath })
        });

        const data = await response.json();

        if (data.success) {
          this.loadFiles(window);
        } else {
          alert('❌ 删除失败: ' + data.error);
        }
      } catch (error) {
        alert('❌ 删除失败: ' + error.message);
      }

      this.closeContextMenu();
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

    isPreviewable(file) {
      return this.isImage(file) || this.isVideo(file) || this.isAudio(file) ||
             this.isPdf(file) || this.isText(file);
    },

    // 文件: static/desktop.app.js

async previewFile(window, file) {
  if (file.is_dir) {
    alert('无法预览文件夹');
    return;
  }
  if (!this.isPreviewable(file)) {
    alert(`不支持预览此文件格式`);
    return;
  }
  const fullPath = this.buildFullPath(window, file.name);
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

  // 其他文件类型逻辑
  const url = `/api/download?path=${encodeURIComponent(fullPath)}&token=${encodeURIComponent(token)}`;
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
    // 文件: static/desktop.app.js
// ... 在 methods 对象内 ...

createPdfPreviewSession: async function(filePath, token) {
  try {
    const response = await axios.post('/api/create-preview-session', {
      file_path: filePath,
      file_type: 'pdf'
    });
    if (response.data.success && response.data.session_id) {
      return `/api/preview-session/${response.data.session_id}`;
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

  const fullPath = this.buildFullPath(window, file.name);

  // 显示分享对话框
  const password = prompt('设置分享密码(可选，直接确定则无密码):');
  const expireHours = prompt('有效期(小时):', '24');

  if (expireHours === null) return; // 用户取消

  try {
    const response = await fetch('/api/share', {
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
      // 显示分享链接
      const shareUrl = data.full_url || window.location.origin + data.share_url;

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

// ... (您已有的其他方法) ...

// [新增] 永久解密磁盘的方法
async decryptDiskPermanently(drive) {
    // 风险提示 1
    if (!confirm(`⚠️ 警告：这是一个高风险操作！\n\n您确定要永久解密磁盘 [${drive}] 吗？\n此操作会将所有文件还原为明文，且不可逆。`)) {
        return;
    }
    // 风险提示 2：要求用户输入盘符确认
    const confirmation = prompt(`为确认操作，请输入要解密的磁盘盘符 (例如: ${drive})`);
    if (confirmation !== drive) {
        this.showToast('输入不匹配，操作已取消', 'info');
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

        // 这里的消息只是告诉用户任务已启动
        alert(response.data.message);

        // 稍等片刻后刷新状态，让用户看到变化（最终完成需要看后台日志）
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

    // ==========================================
    // 用户管理
    // ==========================================
    async openUserManagement() {
      const window = this.createWindow('users', '用户管理', '👥', {
        width: 900,
        height: 650,
        users: [],
        loading: true,
        editingUser: null,
        newPassword: ''
      });
      this.showStartMenu = false;
      await this.loadUsers(window);
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
      this.createWindow('system', '系统信息', '📊');
      this.showStartMenu = false;
    },

    openDiskWindow() {
      this.createWindow('disks', '磁盘管理', '💿', {
        activeTab: 'ec',  // 默认标签页: ec, encryption, raid
        width: 900,
        height: 650
      });
      this.showStartMenu = false;
    },

    openECConfig() {
      // 打开磁盘管理窗口并切换到纠删码标签页
      const window = this.createWindow('disks', '磁盘管理', '💿', {
        activeTab: 'ec',
        width: 900,
        height: 650
      });
      this.showStartMenu = false;
    },

    openECDetailConfig() {
      alert('打开纠删码详细配置\n(跳转到传统配置界面)');
    },

    openEncryptionConfig() {
      alert('打开磁盘加密配置\n(跳转到传统配置界面)');
    },


    // ==========================================
    // 任务栏
    // ==========================================
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

    // ==========================================
    // 工具方法
    // ==========================================
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

  // ✅ 加密文件显示锁图标
  if (filename.endsWith('.encrypted')) {
    return '🔒';
  }

  const ext = filename.split('.').pop().toLowerCase();
  const icons = {
    txt: '📄', pdf: '📕', doc: '📘', docx: '📘',
    jpg: '🖼️', png: '🖼️', gif: '🖼️',
    mp3: '🎵', mp4: '🎬', avi: '🎬',
    zip: '📦', rar: '📦'
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
    showToast(message, type = 'info') {
      // 创建toast元素
      const toast = document.createElement('div');
      toast.textContent = message;
      toast.className = `fixed top-20 left-1/2 transform -translate-x-1/2 px-6 py-3 rounded-lg shadow-lg text-white font-semibold z-[9999] transition-all duration-300`;

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
        toast.style.opacity = '0';
        toast.style.transform = 'translate(-50%, -20px)';
      }, 2000);

      setTimeout(() => {
        document.body.removeChild(toast);
      }, 2500);
    }  // ⚠️ 注意:最后一个方
  },


  mounted() {
    // 更新时间
    this.updateTime();
    setInterval(this.updateTime, 1000);

    // 阻止默认右键菜单
    document.addEventListener('contextmenu', (e) => {
      if (this.loggedIn) {
        e.preventDefault();
      }
    });

    // 点击关闭右键菜单
    document.addEventListener('click', () => {
      if (this.contextMenu.show) {
        this.closeContextMenu();
      }
      if (this.showStartMenu) {
        this.showStartMenu = false;
      }
    });

    // 检查是否已登录
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');
    if (token && userData) {
      try {
        axios.defaults.headers.common['Authorization'] = 'Bearer ' + token;
        this.user = JSON.parse(userData);
        this.loggedIn = true;
        this.loadData();
      } catch (e) {
        this.logout();
      }
    }
  }
}).mount('#app');