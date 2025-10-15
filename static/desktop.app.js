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

    downloadFile(window, file) {
      const fullPath = this.buildFullPath(window, file.name);
      const token = localStorage.getItem('token');
      const url = `/api/download?path=${encodeURIComponent(fullPath)}&token=${encodeURIComponent(token)}`;
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
            label: file.is_dir ? '打开' : '下载',
            action: () => this.handleDoubleClick(window, file)
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

    async createNewFolder(window) {
      const name = prompt('请输入文件夹名称:');
      if (!name) return;

      try {
        const response = await fetch('/api/mkdir', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            parent: window.currentPath,
            name: name
          })
        });

        const data = await response.json();

        if (data.success) {
          this.loadFiles(window);
        } else {
          alert('❌ 创建失败: ' + data.error);
        }
      } catch (error) {
        alert('❌ 创建失败: ' + error.message);
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
    }
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