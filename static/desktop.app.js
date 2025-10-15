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
          this.fetchEcStatus()
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
      this.windows.push(window);
      this.showStartMenu = false;
      return window;
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
        isLocked: false,
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
        storage.push({
          icon: '💾',
          label: `${driveLabel} 盘`,
          path: drive.drive,
          type: 'physical',
          usage: diskInfo ? diskInfo.percent : 0
        });
      });

      // 添加 EC 卷 (放在最前面,使其更醒目)
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

    async loadFiles(window) {
      const token = localStorage.getItem('token');
      if (!token) {
        alert('未登录');
        return;
      }

      // 构建完整路径
      let fullPath;
      if (window.currentDrive === 'ec_volume') {
        fullPath = window.currentPath.startsWith('ec_volume')
          ? window.currentPath
          : 'ec_volume';
      } else {
        const cleanPath = window.currentPath.replace(/^\//, '');
        fullPath = window.currentDrive + cleanPath;
      }

      try {
        const response = await fetch(`/api/list?path=${encodeURIComponent(fullPath)}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.success) {
          window.files = data.items || [];
          this.sortFiles(window);
        } else {
          alert('❌ 加载失败: ' + (data.error || '未知错误'));
        }
      } catch (error) {
        console.error('加载文件列表失败:', error);
        alert('❌ 加载失败: ' + error.message);
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
        this.downloadFile(window, file);
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

    renameSelected(window) {
      if (window.selectedFiles.length !== 1) {
        alert('请选择一个文件或文件夹进行重命名');
        return;
      }

      const oldName = window.selectedFiles[0];
      const newName = prompt('请输入新名称:', oldName);

      if (!newName || newName === oldName) return;

      this.renameFile(window, { name: oldName }, newName);
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
        }
      },
      {
        icon: '📥',
        label: '下载',
        action: () => this.downloadFile(window, file),
        disabled: file.is_dir
      },
      {
        icon: '🔗',
        label: '分享',
        action: () => this.shareFile(window, file),
        disabled: file.is_dir
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

    renameFile(window, file, newName) {
      if (!newName) {
        const currentName = file.name || file;
        newName = prompt('请输入新名称:', typeof currentName === 'string' ? currentName : currentName.name);
      }

      if (!newName) return;

      const oldName = typeof file === 'string' ? file : file.name;
      if (newName === oldName) return;

      alert(`重命名功能: ${oldName} → ${newName}\n(API 对接中...)`);
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

      try {
        // 创建预览窗口
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

        // PDF 使用会话预览方案
        if (this.isPdf(file)) {
          console.log('开始创建PDF预览会话...');
          console.log('文件路径:', fullPath);

          try {
            const sessionUrl = await this.createPdfPreviewSession(fullPath, token);
            console.log('PDF预览会话创建成功!');
            console.log('会话URL:', sessionUrl);

            // 设置预览内容
            previewWindow.previewContent = sessionUrl;
            previewWindow.isLoading = false;

            // 调试: 检查窗口状态
            console.log('=== 预览窗口最终状态 ===');
            console.log('窗口ID:', previewWindow.id);
            console.log('窗口类型:', previewWindow.type);
            console.log('文件类型:', previewWindow.fileType);
            console.log('预览内容URL:', previewWindow.previewContent);
            console.log('是否加载中:', previewWindow.isLoading);
            console.log('是否有错误:', previewWindow.previewError);
            console.log('完整窗口对象:', JSON.stringify(previewWindow, null, 2));

            // 延迟检查iframe是否加载
            setTimeout(() => {
              console.log('\n=== 1秒后检查DOM ===');
              const iframes = document.querySelectorAll('iframe');
              console.log('页面中的iframe数量:', iframes.length);

              if (iframes.length === 0) {
                console.error('❌ iframe未被渲染!');
                console.log('可能原因:');
                console.log('1. Vue条件渲染未匹配');
                console.log('2. window.fileType !== "pdf"');
                console.log('3. HTML模板问题');

                // 检查预览窗口元素
                const previewDivs = document.querySelectorAll('[class*="preview"]');
                console.log('包含preview的div数量:', previewDivs.length);

                // 检查所有窗口
                const allWindows = document.querySelectorAll('.window');
                console.log('所有窗口数量:', allWindows.length);
                allWindows.forEach((win, i) => {
                  console.log(`窗口 ${i}:`, win.querySelector('.window-header')?.textContent);
                });
              } else {
                console.log('✅ 找到iframe');
                iframes.forEach((iframe, index) => {
                  console.log(`iframe ${index}:`, {
                    src: iframe.src,
                    width: iframe.offsetWidth,
                    height: iframe.offsetHeight,
                    display: window.getComputedStyle(iframe).display
                  });
                });
              }
            }, 1000);

          } catch (error) {
            console.error('PDF预览会话创建失败:', error);
            previewWindow.previewError = 'PDF预览失败: ' + error.message;
            previewWindow.isLoading = false;
          }
          return;
        }

        // 其他格式使用 download 接口
        const url = `/api/download?path=${encodeURIComponent(fullPath)}&token=${encodeURIComponent(token)}`;

        if (this.isImage(file) || this.isVideo(file) || this.isAudio(file)) {
          // 图片、视频、音频直接使用URL
          previewWindow.previewContent = url;
          previewWindow.isLoading = false;
        } else if (this.isText(file)) {
          // 文本文件需要获取内容
          try {
            const response = await fetch(url);
            if (response.ok) {
              const text = await response.text();
              previewWindow.previewContent = text;
              previewWindow.isLoading = false;
            } else {
              previewWindow.previewError = '文本加载失败';
              previewWindow.isLoading = false;
            }
          } catch (err) {
            previewWindow.previewError = '文本加载异常: ' + err.message;
            previewWindow.isLoading = false;
          }
        }
      } catch (error) {
        console.error('预览文件失败:', error);
        alert('预览失败: ' + error.message);
      }
    },

// 创建PDF预览会话
async createPdfPreviewSession(filePath, token) {
  try {
    console.log('正在创建PDF预览会话...');
    console.log('文件路径:', filePath);
    console.log('Token:', token ? '已提供' : '未提供');

    const response = await axios.post('/api/create-preview-session', {
      file_path: filePath,
      file_type: 'pdf'
    }, {
      headers: {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
      }
    });

    console.log('=== 后端响应 ===');
    console.log('完整响应:', response.data);
    console.log('success:', response.data.success);
    console.log('session_id:', response.data.session_id);
    console.log('message:', response.data.message);

    if (response.data.success && response.data.session_id) {
      const sessionUrl = `/api/preview-session/${response.data.session_id}`;
      console.log('✅ 生成的会话URL:', sessionUrl);

      // 立即测试会话是否可访问
      console.log('测试会话访问...');
      const testResponse = await fetch(sessionUrl);
      console.log('会话测试响应状态:', testResponse.status);

      if (!testResponse.ok) {
        const errorData = await testResponse.json();
        console.error('❌ 会话访问失败:', errorData);
        throw new Error('会话创建后立即失效: ' + (errorData.error || '未知错误'));
      }

      console.log('✅ 会话可以正常访问');
      return sessionUrl;
    } else {
      throw new Error(response.data.error || '创建预览会话失败');
    }
  } catch (error) {
    console.error('❌ 创建PDF预览会话失败:', error);

    // 详细的错误处理
    if (error.response) {
      if (error.response.status === 401) {
        throw new Error('登录已过期,请重新登录');
      } else if (error.response.status === 404) {
        throw new Error('文件不存在');
      } else if (error.response.status === 403) {
        throw new Error('没有访问权限');
      } else {
        throw new Error('创建预览会话失败: ' + (error.response.data?.error || `HTTP ${error.response.status}`));
      }
    } else if (error.request) {
      throw new Error('网络请求失败,请检查网络连接');
    } else {
      throw new Error('创建预览会话失败: ' + error.message);
    }
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

    openUserManagement() {
      alert('打开用户管理窗口');
      this.showStartMenu = false;
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