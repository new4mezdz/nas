const { createApp } = Vue;
createApp({
      data() {
        return {
          loggedIn: false,
          user: { username: '', is_admin: false },
          showRegister: false,
          loginForm: { username: '', password: '' },
          registerForm: { username: '', password: '', confirm: '' },
          errorMessage: '',
          infoMessage: '',

          // 桌面系统
          windows: [],
          nextWindowId: 1,
          maxZIndex: 100,
          dragging: null,

          // 任务栏
          showStartMenu: false,
          currentTime: '',

          // 右键菜单
          contextMenu: {
            show: false,
            x: 0,
            y: 0,
            items: []
          },

          // 数据
          systemInfo: {},
          disks: [],
          availableDrives: [],
          ecStatus: { is_configured: false },

          // 对话框
          showUploadDialog: false
        }
      },

      methods: {
        // 模拟登录
        login() {
          if (this.loginForm.username && this.loginForm.password) {
            this.loggedIn = true;
            this.user = { username: this.loginForm.username, is_admin: true };
            this.loadData();
          } else {
            this.errorMessage = '请输入用户名和密码';
          }
        },

        register() {
          if (this.registerForm.password !== this.registerForm.confirm) {
            this.errorMessage = '两次密码输入不一致';
            return;
          }
          this.infoMessage = '注册成功,请登录';
          this.showRegister = false;
        },

        logout() {
          this.loggedIn = false;
          this.windows = [];
          this.showStartMenu = false;
        },

        // 窗口管理
        createWindow(type, title, icon, data = {}) {
          const window = {
            id: this.nextWindowId++,
            type,
            title,
            icon,
            x: 100 + (this.windows.length * 30),
            y: 50 + (this.windows.length * 30),
            width: 800,
            height: 600,
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

        // 文件操作
        openFilesWindow(drive) {
          const window = this.createWindow('files', drive, '📁', {
            drive,
            currentPath: drive,
            files: [],
            history: [drive]
          });
          this.loadFiles(window);
        },

        loadFiles(window) {
          // 模拟数据
          window.files = [
            { name: 'Documents', is_dir: true },
            { name: 'Pictures', is_dir: true },
            { name: 'Videos', is_dir: true },
            { name: 'file.txt', is_dir: false, size: 1024 },
            { name: 'photo.jpg', is_dir: false, size: 2048000 },
            { name: 'video.mp4', is_dir: false, size: 10485760 }
          ];
        },

        refreshFiles(window) {
          this.loadFiles(window);
        },

        goBack(window) {
          if (window.history.length > 1) {
            window.history.pop();
            window.currentPath = window.history[window.history.length - 1];
            this.loadFiles(window);
          }
        },

        openFile(window, file) {
          if (file.is_dir) {
            window.history.push(window.currentPath + '/' + file.name);
            window.currentPath = window.history[window.history.length - 1];
            this.loadFiles(window);
          } else {
            alert('打开文件: ' + file.name);
          }
        },

        getFileIcon(filename) {
          const ext = filename.split('.').pop().toLowerCase();
          const icons = {
            txt: '📄', pdf: '📕', doc: '📘', docx: '📘',
            jpg: '🖼️', png: '🖼️', gif: '🖼️',
            mp3: '🎵', mp4: '🎬', avi: '🎬',
            zip: '📦', rar: '📦'
          };
          return icons[ext] || '📄';
        },

        // 系统窗口
        openSystemWindow() {
          this.createWindow('system', '系统信息', '📊');
          this.showStartMenu = false;
        },

        openDiskWindow() {
          this.createWindow('disks', '磁盘管理', '💿');
          this.showStartMenu = false;
        },

        openECConfig() {
          alert('打开纠删码配置窗口');
          this.showStartMenu = false;
        },

        openUserManagement() {
          alert('打开用户管理窗口');
          this.showStartMenu = false;
        },

        showNewFolderDialog(window) {
          const name = prompt('请输入文件夹名称:');
          if (name) {
            window.files.unshift({
              name: name,
              is_dir: true
            });
          }
        },

        // 右键菜单
        showDesktopMenu(event) {
          this.contextMenu = {
            show: true,
            x: event.clientX,
            y: event.clientY,
            items: [
              { icon: '📁', label: '新建文件夹', action: () => this.newFolder() },
              { icon: '📄', label: '新建文件', action: () => this.newFile() },
              { separator: true },
              { icon: '🔄', label: '刷新桌面', action: () => this.refresh() },
              { separator: true },
              { icon: '⚙️', label: '设置', action: () => this.openSettings() }
            ]
          };
        },

        showFileContextMenu(event, file, window) {
          this.contextMenu = {
            show: true,
            x: event.clientX,
            y: event.clientY,
            items: [
              { icon: '📂', label: '打开', action: () => this.openFile(window, file) },
              { separator: true },
              { icon: '✏️', label: '重命名', action: () => this.renameFile(file) },
              { icon: '🗑️', label: '删除', action: () => this.deleteFile(window, file) },
              { separator: true },
              { icon: '📋', label: '属性', action: () => this.showProperties(file) }
            ]
          };
        },

        showFileMenu(event, drive) {
          this.contextMenu = {
            show: true,
            x: event.clientX,
            y: event.clientY,
            items: [
              { icon: '📂', label: '打开', action: () => this.openFilesWindow(drive.drive) },
              { separator: true },
              { icon: '📊', label: '属性', action: () => this.showDiskProperties(drive) }
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

        // 右键菜单操作
        newFolder() {
          const name = prompt('请输入文件夹名称:');
          if (name) {
            alert('创建文件夹: ' + name);
          }
          this.closeContextMenu();
        },

        newFile() {
          alert('创建新文件');
          this.closeContextMenu();
        },

        refresh() {
          this.loadData();
          this.closeContextMenu();
        },

        openSettings() {
          alert('打开设置');
          this.closeContextMenu();
        },

        renameFile(file) {
          const newName = prompt('请输入新名称:', file.name);
          if (newName && newName !== file.name) {
            file.name = newName;
          }
          this.closeContextMenu();
        },

        deleteFile(window, file) {
          if (confirm('确认删除 ' + file.name + '?')) {
            window.files = window.files.filter(f => f !== file);
          }
          this.closeContextMenu();
        },

        showProperties(file) {
          alert('文件属性:\n名称: ' + file.name + '\n大小: ' + this.formatSize(file.size));
          this.closeContextMenu();
        },

        showDiskProperties(drive) {
          alert('磁盘属性:\n' + drive.drive);
          this.closeContextMenu();
        },

        // 任务栏
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

        // 数据加载
        loadData() {
          // 模拟系统信息
          this.systemInfo = {
            hostname: 'NAS-Server',
            os: 'Linux 5.15.0',
            cpu_percent: 15,
            memory_total: 8589934592,
            memory_used: 4294967296
          };

          // 模拟磁盘信息
          this.disks = [
            { mount: 'D:/', bytes_total: 1000000000000, bytes_used: 400000000000, bytes_free: 600000000000, percent: 40 },
            { mount: 'E:/', bytes_total: 2000000000000, bytes_used: 800000000000, bytes_free: 1200000000000, percent: 40 },
            { mount: 'F:/', bytes_total: 3000000000000, bytes_used: 900000000000, bytes_free: 2100000000000, percent: 30 }
          ];

          // 模拟可用驱动器
          this.availableDrives = [
            { drive: 'D:/' },
            { drive: 'E:/' },
            { drive: 'F:/' }
          ];

          // 模拟纠删码状态
          this.ecStatus = {
            is_configured: true,
            is_healthy: true
          };
        },

        // 工具方法
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
      }
    }).mount('#app');