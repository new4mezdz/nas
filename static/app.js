const app = Vue.createApp({
  data() {
    return {
      // 登录/注册
      showRegister: false,
      loggedIn: false,
      loginForm: { username: '', password: '' },
      registerForm: { username: '', password: '', confirm: '' },
      user: { username: '', is_admin: false },

      // 系统/磁盘信息
      systemInfo: { hostname: '', os: '', cpu_percent: 0, memory_total: 0, memory_used: 0, uptime: 0 },
      disks: [],

      // 文件管理
      currentPath: '/',
      currentDrive: 'D:/', // 当前盘符
      availableDrives: [], // 可用盘符列表
      fileList: [],
      newDirName: '',
      uploadTargetDir: '/',
      allDirs: ['/'],
      uploadInfo: '',
      selectedFiles: [],

      // 上传
      showUploadDialog: false,
      uploadFiles: [],
      dragOver: false,
      uploadStatus: '',

      // 文件操作 - 重命名相关
      renaming: null,
      renameTo: '',
      adminOnlyMsg: '',

      // 用户管理
      userList: [],
      showUserAdmin: false,

      // 修改密码弹窗
      showChangePw: false,
      pwForm: { old_password: '', new_password: '', confirm: '' },
      pwMsg: '',

      // 管理员重置密码弹窗
      resetUser: null,
      resetPwForm: { new_password: '', confirm: '' },
      resetPwMsg: '',

      // 错误/提示
      errorMessage: '',
      infoMessage: '',
      sambaMessage: '',

      // 搜索
      searchTimer: null,
      showSearchDialog: false,
      searchKeyword: '',
      searchScope: 'current', // or 'all'
      searchResults: [],

      // 预览
      showPreview: false,
      previewingFile: null,
      previewUrl: '',
      previewType: '',
      textContent: '',

      // 分享
      shareDialogVisible: false,
      shareFile: null,
      shareExpire: 24,
      sharePassword: '',
      shareUrl: '',

      // 纠删码
      ecDialogVisible: false,
      ecScheme: 'rs',
      k: 4,
      m: 2,
      selectedDisks: [],
      ec: {             // <--- 关键：创建一个 ec 对象
       config: null   }, // <--- 在 ec 对象内部初始化 config

      // ========== 新增：纠删码健康状态与恢复 ==========
      ecStatus: {
        is_configured: false,
        is_healthy: true,
        lost_disks: [],
        available_new_disks: [],
        can_rebuild: false
      },
      showEcRecoverDialog: false,
      recoveryPayload: {
        lost_disk: '',
        new_disk: ''
      },
      // 协作分享弹窗
      showCollabShareDialog: false,
      collabShareFile: null,
      collabSharePassword: '',
      collabShareExpire: 24,
      collabShareUrl: '',
      collabShareError: '',
    }
  },

  computed: {
     // 文件: app.js -> computed

navigableLocations() {
  // 1. 获取所有参与了纠删码的磁盘挂载点，并对路径进行归一化
  const ecDisks = this.disks.filter(d => d.ec_scheme);
  // 关键：Set 中存储归一化后的路径，用于快速查找
  const ecDiskMounts = new Set(ecDisks.map(d => this.normalizePath(d.mount)));

  // 2. 如果存在纠删码配置（即 EC 盘符集合非空）...
  if (ecDiskMounts.size > 0) {
    const locations = [];

    // a. 始终添加 '[纠删码卷]' 选项
    locations.push({
      name: '[纠删码卷]',
      path: 'ec_volume'
    });

    // b. 筛选未参与纠删码的物理磁盘
    const nonEcDrives = this.availableDrives.filter(driveObj => {
      // 对 availableDrives 中的路径也进行归一化后再进行查找
      return !ecDiskMounts.has(this.normalizePath(driveObj.drive));
    });

    // c. 将非 EC 物理磁盘添加到列表中
    nonEcDrives.forEach(driveObj => {
      locations.push({
        name: `物理磁盘 (${driveObj.drive})`,
        path: driveObj.drive
      });
    });

    return locations;
  }
  // 3. 如果不存在纠删码配置，则显示所有物理磁盘。
  else {
    return this.availableDrives.map(driveObj => ({
      name: `物理磁盘 (${driveObj.drive})`,
      path: driveObj.drive
    }));
  }
},

  // ===== 其他既有的计算属性保持不变 =====
  ecDiskGroup() {
    const ecDisks = this.disks.filter(d => d.ec_scheme);
    if (ecDisks.length === 0) {
      return null;
    }
    const total = ecDisks.reduce((sum, disk) => sum + disk.total, 0);
    const used = ecDisks.reduce((sum, disk) => sum + disk.used, 0);
    return {
      total,
      used,
      percent: total > 0 ? Math.round((used / total) * 100) : 0,
      ec_scheme: ecDisks[0].ec_scheme
    };
  },
  nonECDiskList() {
    return this.disks.filter(d => !d.ec_scheme);
  },
  isAnyFileSelected() {
    return this.selectedFiles.length > 0;
  },
  selectAll: {
    get() {
      return this.fileList.length > 0 && this.selectedFiles.length === this.fileList.length;
    },
    set(value) {
      this.selectedFiles = value ? [...this.fileList] : [];
    }
  },
  breadcrumbs() {
    if (this.currentPath.startsWith('ec_volume')) {
        const base = [{ name: '[纠删码卷]', path: 'ec_volume' }];
        const subPath = this.currentPath.substring('ec_volume'.length).replace(/^\//, '');
        if (!subPath) return base;

        const parts = subPath.split('/').filter(p => p);
        let path = 'ec_volume';
        for (const part of parts) {
            path += '/' + part;
            base.push({ name: part, path: path });
        }
        return base;
    }

    if (this.currentPath === '/') return [{ name: `根目录 (${this.currentDrive})`, path: '/' }];
    const parts = this.currentPath.split('/').filter(p => p);
    let path = '';
    const crumbs = [{ name: `根目录 (${this.currentDrive})`, path: '/' }];
    for (const part of parts) {
        path += '/' + part;
        crumbs.push({ name: part, path: path });
    }
    return crumbs;
  }
  // ==========================
  },

  methods: {
    // 文件: app.js -> methods (在您已有的方法中找个位置添加)

// ...
// ========== 新增路径归一化辅助方法 ==========
normalizePath(p) {
  if (!p) return '';
  // 统一转大写、反斜杠转正斜杠、去除末尾斜杠
  return p.toUpperCase().replace(/\\/g, '/').replace(/\/$/, '');
},
// ===================================
// ...

    // ========== 停止系统信息定时刷新 ==========
    stopSysTimer() {
      if (this._sysTimer) {
        clearInterval(this._sysTimer);
        this._sysTimer = null;
      }
    },
       // 在 methods 中添加这两个函数
    goECVolume() {
  // 点击纠删码卷时，加载其文件列表
  this.loadFileList('ec_volume');
},
    goDisk(mount) {
  // 点击物理磁盘时，切换当前盘符并加载根目录
  this.currentDrive = mount;
  this.loadFileList('/');
},
    // 登录、注册、登出
    showLoginForm() {
      this.showRegister = false; this.errorMessage = ''; this.infoMessage = '';
    },
    showRegisterForm() {
      this.showRegister = true; this.errorMessage = ''; this.infoMessage = '';
    },
    async login() {
      this.errorMessage = ''; this.infoMessage = '';
      if (!this.loginForm.username || !this.loginForm.password) {
        this.errorMessage = '请输入用户名和密码'; return;
      }
      try {
        const res = await axios.post('/api/login', {
          username: this.loginForm.username,
          password: this.loginForm.password
        });
        const data = res.data;
        localStorage.setItem('token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        axios.defaults.headers.common['Authorization'] = 'Bearer ' + data.token;
        this.user = data.user;
        this.loggedIn = true;
        this.loginForm.password = '';
        await this.loadMainPanel();
      } catch (err) {
        this.errorMessage = err.response?.data?.error || '登录失败';
      }
    },
    async register() {
      this.errorMessage = ''; this.infoMessage = '';
      if (!this.registerForm.username || !this.registerForm.password) {
        this.errorMessage = '请输入用户名和密码'; return;
      }
      if (this.registerForm.password !== this.registerForm.confirm) {
        this.errorMessage = '两次密码输入不一致'; return;
      }
      try {
        const res = await axios.post('/api/register', {
          username: this.registerForm.username,
          password: this.registerForm.password
        });
        this.infoMessage = '注册成功，请登录';
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
      this.systemInfo = { hostname: '', os: '', cpu_percent: 0, memory_total: 0, memory_used: 0, uptime: 0 };
      this.disks = [];
      this.sambaMessage = '';
      this.errorMessage = '';
      this.infoMessage = '';
      this.showChangePw = false;
      this.pwMsg = '';
      delete axios.defaults.headers.common['Authorization'];
      this.stopSysTimer();
    },

    // ========== 修改密码 ==========
    showChangePasswordForm() {
      this.showChangePw = true;
      this.pwForm.old_password = '';
      this.pwForm.new_password = '';
      this.pwForm.confirm = '';
      this.pwMsg = '';
    },
    async changePassword() {
      this.pwMsg = '';
      if (!this.pwForm.old_password || !this.pwForm.new_password) {
        this.pwMsg = "请输入完整信息";
        return;
      }
      if (this.pwForm.new_password !== this.pwForm.confirm) {
        this.pwMsg = "新密码确认不一致";
        return;
      }
      try {
        const res = await axios.patch('/api/change_password', {
          old_password: this.pwForm.old_password,
          new_password: this.pwForm.new_password
        });
        this.pwMsg = "✅ 密码修改成功";
        setTimeout(() => {
          this.showChangePw = false;
          this.pwMsg = '';
        }, 1500);
      } catch (err) {
        this.pwMsg = err.response?.data?.error || "修改失败";
      }
    },
 // 用这个新版本来替换
// 修改changeDrive方法
// 文件: app.js -> methods
// 文件: app.js -> methods

// ========== 新增辅助方法：构建完整路径 (优化版) ==========
// 文件: app.js -> methods

// ========== 修正版：构建完整路径 (重点修复EC卷根目录拼接) ==========
// 文件: app.js -> methods -> buildFullPath (最终修正版)

// 文件: app.js -> methods -> buildFullPath (最鲁棒版本)

buildFullPath(fileName) {
  // 1. 如果当前盘符是 EC 卷
  if (this.currentDrive === 'ec_volume') {
    let path = this.currentPath.replace(/\\/g, '/');

    // --- 关键清理步骤 ---
    // 目标: 移除所有 'ec_volume' 前缀、开头的 '/' 和末尾的 '/'
    path = path.replace(/^ec_volume\/?/, ''); // 移除 'ec_volume' 或 'ec_volume/'
    path = path.replace(/^\//, '');          // 移除开头的 '/'
    path = path.replace(/\/$/, '');          // 移除末尾的 '/'

    // 最终拼接：
    if (path === '') {
      // 根目录：ec_volume/fileName
      return `ec_volume/${fileName}`;
    }

    // 子目录：ec_volume/dirA/fileName
    return `ec_volume/${path}/${fileName}`;
  }

  // 2. 处理物理硬盘路径 (原逻辑，确保它是正确的绝对路径)
  let cleanPath = this.currentPath;

  if (cleanPath.startsWith('/')) {
    cleanPath = cleanPath.substring(1);
  }

  let fullPath;
  if (cleanPath === '' || cleanPath === '/') {
    // 根目录情况 (例如 D:/fileName)
    fullPath = this.currentDrive + fileName;
  } else {
    // 子目录情况 (例如 D:/dirA/fileName)
    fullPath = this.currentDrive + cleanPath + '/' + fileName;
  }

  // 标准化路径分隔符
  return fullPath.replace(/\\/g, '/');
},
// ===================================
initializeCurrentDrive() {
  const ecDisks = this.disks.filter(d => d.ec_scheme);

  if (ecDisks.length > 0) {
    // 默认选择纠删码卷
    this.currentDrive = 'ec_volume';
  } else if (this.availableDrives.length > 0) {
    // 否则选择第一个物理盘
    this.currentDrive = this.availableDrives[0].drive;
  }
},

changeDrive() {
  const selectedPath = this.currentDrive;

  if (selectedPath === 'ec_volume') {
    this.loadFileList('ec_volume');
  } else {
    this.loadFileList('/');
  }
},
    // 更新用户当前目录
    async updateCurrentDirectory(path) {
      try {
        // 将路径转换为相对路径（去掉开头的/）
        const relativePath = path.startsWith('/') ? path.substring(1) : path;
        await axios.post('/api/current-directory', {
          directory: relativePath
        });
      } catch (err) {
        console.error('更新当前目录失败:', err);
      }
    },

    // ========== 管理员重置用户密码 ==========
    async resetPassword() {
      this.resetPwMsg = '';
      if (!this.resetPwForm.new_password) {
        this.resetPwMsg = "请输入新密码";
        return;
      }
      if (this.resetPwForm.new_password !== this.resetPwForm.confirm) {
        this.resetPwMsg = "两次输入的新密码不一致";
        return;
      }
      try {
        const res = await axios.post('/api/admin/reset_password', {
          username: this.resetUser.username,
          new_password: this.resetPwForm.new_password
        });
        if (res.data && res.data.success) {
          this.resetPwMsg = "重置成功";
          setTimeout(() => {
            this.resetUser = null;
            this.resetPwForm.new_password = '';
            this.resetPwForm.confirm = '';
            this.resetPwMsg = '';
          }, 1000);
        } else {
          this.resetPwMsg = res.data.error || "重置失败";
        }
      } catch (e) {
        this.resetPwMsg = e.response?.data?.error || "重置失败";
      }
    },
    showResetPw(u) {
      this.resetUser = u;
      this.resetPwForm.new_password = '';
      this.resetPwForm.confirm = '';
      this.resetPwMsg = '';
    },

async loadMainPanel() {
  await Promise.all([
    this.fetchSystemInfo(),
    this.fetchDiskInfo(),
    this.fetchAvailableDrives(),
    this.fetchEcStatus() // <--- 在这里添加调用
  ]);

  // 初始化驱动器选择
  this.initializeCurrentDrive();
  await this.loadFileList(this.currentDrive === 'ec_volume' ? 'ec_volume' : '/');
  this.startSysTimer();
},
    // ========== 系统/磁盘信息，动态刷新 ==========
    async fetchSystemInfo() {
      try {
        const res = await axios.get('/api/system');
        this.systemInfo = res.data;
      } catch (e) {
        this.logout();
      }
    },
    // 文件: app.js -> methods
async fetchDiskInfo() {
  try {
    const res = await axios.get('/api/disk');
    this.disks = res.data;
  } catch (e) {
    // 增加日志，方便未来调试
    console.error("刷新磁盘信息失败:", e);

    // 关键：检查错误是否是 401 (未授权)，如果是，说明Token失效
    if (e.response && e.response.status === 401) {
      // 立刻执行登出操作，停止所有定时器并返回登录界面
      this.logout();
    }
  }
},
    // 文件: app.js -> methods
// app.js -> methods -> startSysTimer

startSysTimer() {
  this.stopSysTimer();
  this._sysTimer = setInterval(() => {
    if (this.loggedIn) {
      this.fetchSystemInfo();
      this.fetchDiskInfo();
      this.fetchEcStatus(); // <--- 在这里添加调用
    }
  }, 10000); // 10秒刷新一次
},


    // ========== 文件管理 ==========
    async submitSearch() {
      if (!this.searchKeyword.trim()) {
        alert("请输入关键词！");
        return;
      }

      const token = localStorage.getItem("token");
      const url = `/api/search?keyword=${encodeURIComponent(this.searchKeyword)}&scope=${this.searchScope}&path=${encodeURIComponent(this.currentPath || '/')}`;

      try {
        const res = await fetch(url, {
          headers: { "Authorization": `Bearer ${token}` }
        });
        const data = await res.json();

        if (!data.success) {
          alert("❌ 搜索失败：" + (data.error || "未知错误"));
          return;
        }

        if (data.results.length === 0) {
          alert("🔍 没有找到任何文件");
          return;
        }

        this.searchResults = data.results;
      } catch (e) {
        alert("❌ 网络错误：" + e.message);
      }
    },

    // ===== [最终修复] 重写 goToFile 函数 =====
    goToFile(file) {
      if (file.is_dir) {
        // 后端返回的 file.path 已经是我们需要的、相对于盘符的路径了
        // 例如 'folder' 或 'folder/subfolder'
        this.loadFileList(file.path);
      } else {
        this.previewFile(file);
      }
    },

    loadFileList(path, callback) {
      const token = localStorage.getItem("token");
      let fullPath; // 声明一个变量来存储最终路径

      // [新增逻辑] 检查路径是否是纠删码卷
      if (path.startsWith('ec_volume')) {
        // 如果是，直接使用 'ec_volume' 或 'ec_volume/...' 作为路径
        fullPath = path;
      } else {
        // 如果是普通物理磁盘路径，才拼接盘符
        fullPath = this.currentDrive + path.replace(/^\//, '');
      }

      fetch(`/api/list?path=${encodeURIComponent(fullPath)}`, {
        headers: { "Authorization": `Bearer ${token}` }
      })
        .then(res => {
          if (!res.ok) { // 新增：检查响应状态，更好地处理404等错误
            throw new Error(`服务器错误: ${res.status} ${res.statusText}`);
          }
          return res.json();
        })
        .then(data => {
          if (data.success) {
            this.fileList = data.items;
            this.currentPath = path;

            // [新增逻辑] 只有物理磁盘路径才需要更新到后端
            if (!path.startsWith('ec_volume')) {
              this.updateCurrentDirectory(path);
            }

            if (callback) callback();
          } else {
            alert("❌ 加载失败：" + (data.error || "未知错误"));
          }
        })
        .catch(err => {
            // 新增：捕获 fetch 错误（包括我们自己抛出的）
            console.error("加载文件列表时出错:", err);
            alert("❌ 加载失败：" + err.message);
        });
    },
    goDir(name) {
      // 拼接新路径
      let newPath = this.currentPath;
      if (newPath.endsWith('/')) newPath = newPath.slice(0, -1);
      if (this.currentPath === '/') {
        newPath = '/' + name;
      } else {
        newPath = `${this.currentPath}/${name}`;
      }
      this.loadFileList(newPath);
    },



    formatSize(size) {
      if (!size) return "-";
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let i = 0;
      while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
      return size.toFixed(1) + " " + units[i];
    },
    formatTime(ts) {
      if (!ts) return "-";
      const d = new Date(ts * 1000);
      return d.toLocaleString();
    },

    // 多选操作
    selectAllFiles() {
      this.selectedFiles = this.fileList.map(f => f.name);
    },
    clearAllSelected() {
      this.selectedFiles = [];
    },

    async batchDelete() {
  if (!this.selectedFiles.length) return;
  if (!confirm("确认删除选中的文件/文件夹吗？")) return;

  const errors = [];

  for (const fileName of this.selectedFiles) {
    try {
      // ✅ 使用完整路径
      const fullPath = this.buildFullPath(fileName);
      console.log('批量删除路径:', fullPath); // 调试日志

      await axios.post('/api/delete', { path: fullPath });
    } catch (e) {
      console.error(`删除 ${fileName} 失败:`, e);
      errors.push(fileName);
    }
  }

  this.selectedFiles = [];
  this.loadFileList(this.currentPath);

  if (errors.length > 0) {
    alert(`以下文件删除失败：${errors.join(', ')}`);
  }
},
    onSearchInput() {
      if (this.searchTimer) clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => {
        this.loadFileList(this.currentPath);
      }, 300);
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

    // 文件: app.js -> methods

// 文件: app.js -> methods

async uploadDraggedFiles() {
  if (!this.uploadFiles.length) return;

  // 【✅ 核心修复：确定正确的上传目标路径】
  let uploadPath;
  const currentPathNorm = this.currentPath.replace(/\\/g, '/');

  if (this.currentDrive === 'ec_volume') {
      // 纠删码卷：
      if (currentPathNorm === '/' || currentPathNorm === '') {
          // 在EC根目录，目标路径就是 'ec_volume'
          uploadPath = 'ec_volume';
      } else if (currentPathNorm.startsWith('ec_volume')) {
          // 在EC子目录，目标路径就是 'ec_volume/dirA/dirB'
          uploadPath = currentPathNorm;
      } else {
          // 如果 currentPath 是 '/dirA' 这样的相对路径，我们将其视为 EC 卷下的子目录
          uploadPath = 'ec_volume' + currentPathNorm;
      }

  } else {
      // 物理盘：
      if (currentPathNorm === '/' || currentPathNorm === '') {
          // 物理盘根目录，发送盘符本身，例如 'D:/'
          uploadPath = this.currentDrive;
      } else {
          // 物理盘子目录，发送完整的绝对路径，例如 'D:/dirA/dirB'
          // 注意：this.currentDrive 已经是 D:/，currentPathNorm 是 /dirA/dirB
          uploadPath = this.currentDrive + currentPathNorm;
      }
  }

  // 确保路径不为空
  if (!uploadPath) {
      this.uploadStatus = '❌ 错误：无法确定上传路径';
      return;
  }
  // 确保路径中的分隔符正确（统一使用 /）
  uploadPath = uploadPath.replace(/\\/g, '/').replace(/\/{2,}/g, '/'); // 防止双斜杠

  const token = localStorage.getItem("token");

  for (const file of this.uploadFiles) {
    const formData = new FormData();
    formData.append("file", file);
    // 【关键】将修正后的路径发送给后端
    formData.append("path", uploadPath);

    try {
      // ... (fetch 和后续处理逻辑保持不变) ...
      const res = await fetch("/api/upload", {
        method: "POST",
        headers: {
          Authorization: "Bearer " + token,
        },
        body: formData,
      });
      const data = await res.json();
      if (data.success) {
        this.uploadStatus = `✅ ${file.name} 上传成功`;
        this.loadFileList(this.currentPath);
      } else {
        this.uploadStatus = `❌ ${file.name} 上传失败：${data.error}`;
      }
    } catch (err) {
      this.uploadStatus = `❌ ${file.name} 上传异常：${err.message}`;
    }
  }

  setTimeout(() => {
    this.uploadStatus = '';
    this.uploadFiles = [];
    this.showUploadDialog = false;
  }, 1200);
},

    uploadFile() {
      const file = this.$refs.uploadFileInput.files[0];
      if (!file) {
        this.uploadInfo = "请先选择文件";
        return;
      }

      const formData = new FormData();
      formData.append("file", file);
      formData.append("path", this.currentPath);

      this.uploadInfo = "上传中...";

      fetch("/api/upload", {
        method: "POST",
        headers: {
          Authorization: "Bearer " + localStorage.getItem("token"),
        },
        body: formData,
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.success) {
            this.uploadInfo = data.message || "上传成功";
            this.loadFileList(this.currentPath);
          } else {
            this.uploadInfo = data.error || "上传失败";
          }
        })
        .catch((err) => {
          this.uploadInfo = "上传出错：" + err;
        });
    },



    goParent() {
      if (this.currentPath === '/' || this.currentPath === '') return;

      const parts = this.currentPath.split('/').filter(p => p);
      parts.pop();  // 删除最后一级目录名
      const parentPath = '/' + parts.join('/');
      this.loadFileList(parentPath || '/');
    },

    fileSelected() {
      this.uploadInfo = '';
    },

    async mkdir() {
      if (!this.newDirName) return;
      try {
        const res = await axios.post('/api/mkdir', { parent: this.currentPath, name: this.newDirName });
        if (res.data.success) {
          this.loadFileList(this.currentPath);
          this.newDirName = '';
          this.adminOnlyMsg = '';
        } else {
          this.adminOnlyMsg = res.data.error || '创建目录失败';
        }
      } catch (e) {
        this.adminOnlyMsg = e?.response?.data?.error || '无权限或操作失败';
      }
    },

    async deleteEntry(item) {
  if (!confirm("确认删除 " + item.name + "？")) return;
  try {
    // ✅ 使用完整路径
    const fullPath = this.buildFullPath(item.name);
    console.log('删除请求路径:', fullPath); // 调试日志

    const res = await axios.post('/api/delete', { path: fullPath });
    if (res.data.success) {
      this.loadFileList(this.currentPath);
    }
  } catch (e) {
    console.error('删除失败:', e); // 调试日志
    alert(e?.response?.data?.error || "删除失败");
  }
},

    // ========== 重命名功能（修复后） ==========
    startRename(item) {
      this.renaming = item.name;
      this.renameTo = item.name;

      // 下一个tick时聚焦到输入框
      this.$nextTick(() => {
        // 查找重命名输入框
        const inputs = document.querySelectorAll('input[ref="renameInput"]');
        if (inputs.length > 0) {
          const input = inputs[0];
          input.focus();
          input.select(); // 选中所有文本
        } else {
          // 备用方案：查找当前正在编辑的输入框
          const renameInputs = document.querySelectorAll('tr input[type="text"]');
          for (let input of renameInputs) {
            if (input.value === this.renameTo) {
              input.focus();
              input.select();
              break;
            }
          }
        }
      });
    },
    async submitRename(item) {
  if (!this.renameTo || this.renameTo === item.name) {
    this.cancelRename();
    return;
  }
  try {
    // ✅ 构建包含盘符的完整路径
    const fullPath = this.buildFullPath(item.name);
    console.log('重命名请求路径:', fullPath); // 调试日志

    const res = await axios.post('/api/rename', {
      path: fullPath,
      new_name: this.renameTo
    });

    if (res.data.success) {
      this.loadFileList(this.currentPath);
      this.cancelRename();
    }
  } catch (e) {
    console.error('重命名失败:', e); // 调试日志
    alert(e?.response?.data?.error || '重命名失败');
  }
},

    cancelRename() {
      this.renaming = null;
      this.renameTo = '';
    },

    downloadFile(item) {
    const token = localStorage.getItem('token');
  // ✅ 使用完整路径
  const fullPath = this.buildFullPath(item.name);
  console.log('下载请求路径:', fullPath); // 调试日志
      if (window.Blob && window.URL && window.URL.createObjectURL) {
        fetch('/api/download?path=' + encodeURIComponent(fullPath), {
          headers: {
            'Authorization': 'Bearer ' + token
          }
        })
          .then(res => {
            if (!res.ok) throw new Error('下载失败');
            return res.blob();
          })
          .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = item.name;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
              window.URL.revokeObjectURL(url);
              document.body.removeChild(a);
            }, 100);
          })
          .catch(() => {
            const fallbackUrl = '/api/download?path=' + encodeURIComponent(fullPath) + '&token=' + encodeURIComponent(token);
            window.open(fallbackUrl);
          });
      } else {
        const url = '/api/download?path=' + encodeURIComponent(fullPath) + '&token=' + encodeURIComponent(token);
        window.open(url);
      }
    },

    // ========== 分享 ==========
    openShareDialog(item) {
      this.shareDialogVisible = true;
      this.shareFile = item;
      this.shareExpire = 24;
      this.sharePassword = '';
      this.shareUrl = '';
    },

    async submitShare() {
  if (!this.shareFile) return;
  try {
    // ✅ 使用完整路径
    const fullPath = this.buildFullPath(this.shareFile.name);
    console.log('分享请求路径:', fullPath); // 调试日志

    const res = await axios.post('/api/share', {
      file_path: fullPath,
      expire_hours: this.shareExpire,
      password: this.sharePassword
    });
    if (res.data.success) {
      this.shareUrl = window.location.origin + res.data.share_url;
    }
  } catch (e) {
    console.error('分享失败:', e); // 调试日志
    alert(e?.response?.data?.error || "分享失败");
  }
},
// ========== 新增辅助方法：构建完整路径 =========
// app.js -> methods

    // ========== 新增：纠删码恢复相关方法 ==========

    // 1. 获取EC卷的健康状况
    async fetchEcStatus() {
      try {
        const res = await axios.get('/api/ec_status');
        this.ecStatus = res.data;
      } catch (e) {
        console.error("获取纠删码状态失败:", e);
        // 如果API失败，重置为默认安全状态
        this.ecStatus.is_configured = false;
      }
    },

    // 2. 打开恢复对话框
    openEcRecoverDialog(lostDisk) {
      this.recoveryPayload.lost_disk = lostDisk;
      this.recoveryPayload.new_disk = ''; // 重置下拉选择
      this.showEcRecoverDialog = true;
    },

    // 3. 关闭恢复对话框
    closeEcRecoverDialog() {
      this.showEcRecoverDialog = false;
      this.recoveryPayload.lost_disk = '';
      this.recoveryPayload.new_disk = '';
    },

    // 4. 提交恢复请求
    async submitEcRecover() {
      if (!this.recoveryPayload.new_disk) {
        alert('请选择一块新硬盘用于替换！');
        return;
      }
      if (!confirm(`确认要使用新硬盘 ${this.recoveryPayload.new_disk} 来恢复 ${this.recoveryPayload.lost_disk} 上的数据吗？\n这个过程可能需要很长时间。`)) {
        return;
      }

      this.infoMessage = '正在开始恢复，请勿关闭页面...';
      try {
        const res = await axios.post('/api/ec_recover', this.recoveryPayload);
        if (res.data.success) {
          alert('✅ 恢复成功！\n' + res.data.message);
          this.infoMessage = '';
          this.closeEcRecoverDialog();
          // 立即刷新状态
          this.fetchEcStatus();
          this.fetchDiskInfo();
        } else {
          throw new Error(res.data.error || '未知错误');
        }
      } catch (e) {
        this.errorMessage = '恢复失败: ' + (e.response?.data?.error || e.message);
      }
    },

    // ==========================================
    // ===================================
// 纠删码 (EC)
// ===================================
async openEcDialog() {
  this.ecDialogVisible = true;
  // 使用 this.ec.config
  this.ec.config = null;
  try {
    const res = await axios.get('/api/ec_config');
    if (res.data.success && res.data.config) {
      // 使用 this.ec.config
      this.ec.config = res.data.config;
      this.ecScheme = this.ec.config.scheme;
      this.k = this.ec.config.k;
      this.m = this.ec.config.m;
      this.selectedDisks = this.ec.config.disks;
    } else {
      // 没有配置时，重置表单为默认值
      this.ecScheme = 'rs';
      this.k = 4;
      this.m = 2;
      this.selectedDisks = [];
    }
  } catch (e) {
    alert('加载纠删码配置失败: ' + (e.response?.data?.error || e.message));
    this.ecDialogVisible = false;
  }
},
async loadDisks() {
      try {
        // 向 /api/disk 发送GET请求
        const res = await axios.get('/api/disk');
        // 用返回的数据更新 disks 数组
        this.disks = res.data;
      } catch (e) {
        // 如果出错，在控制台打印错误，避免干扰用户
        console.error("加载磁盘列表失败:", e);
        alert('无法刷新磁盘列表，请检查后端服务。');
      }
    },

    // ========== 纠删码 ==========
    async applyECScheme() {
      if (this.selectedDisks.length < this.k + this.m) {
        alert(`至少需要选择 ${this.k + this.m} 个硬盘`);
        return;
      }
      try {
        const res = await axios.post('/api/ec_config', {
          scheme: this.ecScheme,
          k: this.k,
          m: this.m,
          disks: this.selectedDisks
        });
        if (res.data.success) {
          alert('纠删码配置已应用');

          // ===== 新增的关键代码：在成功后立即更新前端状态 =====
          // 后端在保存成功后会返回新的配置信息，我们用它来更新 this.ec.config
          this.ec.config = res.data.config;
          // =================================================

          this.ecDialogVisible = false;
          this.loadDisks(); // 重新加载磁盘信息
        } else {
          alert('应用失败: ' + res.data.error);
        }
      } catch (e) {
        alert('应用配置时出错: ' + (e.response?.data?.error || e.message));
      }
    },

    // ========== 文件预览 ==========
    isPreviewable(file) {
      return (
        this.isImage(file) ||
        this.isVideo(file) ||
        this.isAudio(file) ||
        this.isPdf(file) ||
        this.isText(file) ||
        this.isDocx(file)
      );
    },

    isImage(file) {
      return /\.(jpg|jpeg|png|gif|bmp|webp)$/i.test(file.name);
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
    isDocx(file) {
      return /\.docx$/i.test(file.name);
    },

   previewFile(file) {
  this.previewingFile = file;

  // ✅ 使用完整路径构建（包含盘符）
  const fullPath = this.buildFullPath(file.name);
  console.log('预览请求路径:', fullPath);

  const token = localStorage.getItem('token');
  if (!token) {
    alert('登录已过期，请重新登录');
    this.logout();
    return;
  }

  // 文本类文件
  if (this.isText(file)) {
    this.previewType = 'text';
    this.fetchTextContent(`/api/preview?path=${encodeURIComponent(fullPath)}`);
    this.showPreview = true;
    return;
  }

  // ========== PDF预览 - 使用临时会话方案 ==========
  if (this.isPdf(file)) {
    console.log('开始创建PDF预览会话...');
    this.createPdfPreviewSession(fullPath, token).then(sessionUrl => {
      console.log('PDF预览会话创建成功:', sessionUrl);
      this.previewUrl = sessionUrl;
      this.previewType = 'pdf';
      this.showPreview = true;
    }).catch(error => {
      console.error('PDF预览会话创建失败:', error);
      alert('PDF预览失败：' + error.message);
    });
    return;
  }

  // DOCX 文件
  if (this.isDocx(file)) {
    this.createOnlyOfficeDocument(fullPath, file.name).then(docId => {
      const onlyofficeUrl = `/onlyoffice-edit.html?doc_id=${docId}&mode=view`;
      window.open(onlyofficeUrl, '_blank');
    }).catch(err => {
      alert("创建 OnlyOffice 文档失败：" + (err.response?.data?.error || '网络错误'));
    });
    return;
  }

  // 其他图片/音频/视频
  const baseApi = `/api/preview?path=${encodeURIComponent(fullPath)}`;
  axios.get(baseApi, {
    responseType: 'blob',
    headers: { Authorization: 'Bearer ' + token }
  }).then(res => {
    this.previewUrl = URL.createObjectURL(res.data);
    if (this.isImage(file)) this.previewType = 'image';
    else if (this.isVideo(file)) this.previewType = 'video';
    else if (this.isAudio(file)) this.previewType = 'audio';
    else this.previewType = 'other';
    this.showPreview = true;
  }).catch(err => {
    console.error("预览失败:", err);
    alert("预览失败：" + (err.response?.data?.error || '网络错误'));
  });
},
// ========== 新增：创建PDF预览会话方法 ==========
async createPdfPreviewSession(filePath, token) {
  try {
    console.log('正在创建PDF预览会话，文件路径:', filePath);

    const response = await axios.post('/api/create-preview-session', {
      file_path: filePath,
      file_type: 'pdf'
    }, {
      headers: {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
      }
    });

    console.log('预览会话API响应:', response.data);

    if (response.data.success) {
      const sessionUrl = `/api/preview-session/${response.data.session_id}`;
      console.log('生成的会话URL:', sessionUrl);
      return sessionUrl;
    } else {
      throw new Error(response.data.error || '创建预览会话失败');
    }
  } catch (error) {
    console.error('创建PDF预览会话失败:', error);

    // 详细的错误处理
    if (error.response) {
      if (error.response.status === 401) {
        throw new Error('登录已过期，请重新登录');
      } else if (error.response.status === 404) {
        throw new Error('文件不存在');
      } else if (error.response.status === 403) {
        throw new Error('没有访问权限');
      } else {
        throw new Error('创建预览会话失败: ' + (error.response.data?.error || `HTTP ${error.response.status}`));
      }
    } else if (error.request) {
      throw new Error('网络请求失败，请检查网络连接');
    } else {
      throw new Error('创建预览会话失败: ' + error.message);
    }
  }
},
// ===================================
    // 纠删码 (EC) - 新增/修改的函数
    // ===================================

    async deleteEcConfig() {
      if (!confirm('您确定要删除纠删码配置吗？\n此操作不可逆！')) {
        return;
      }
      try {
        const res = await axios.delete('/api/ec_config');
        if (res.data.success) {
          alert('纠删码配置已删除。');
          this.ecConfig = null; // 清空前端的配置
          this.ecDialogVisible = false; // 关闭弹窗
          this.loadDisks(); // 重新加载磁盘信息以更新状态
        } else {
          alert('删除失败: ' + (res.data.error || '未知错误'));
        }
      } catch (e) {
        alert('删除配置时出错: ' + (e.response?.data?.error || e.message));
      }
    },


    // ========== 修复fetchTextContent ==========
async fetchTextContent(url) {
  const token = localStorage.getItem('token');

  if (!token) {
    this.textContent = '⚠️ 登录已过期，请重新登录';
    return;
  }

  try {
    const response = await fetch(url, {
      headers: {
        Authorization: "Bearer " + token
      }
    });

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('登录已过期，请重新登录');
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    }

    const content = await response.text();
    this.textContent = content;
  } catch (err) {
    console.error('获取文本内容失败:', err);
    this.textContent = '⚠️ 加载失败: ' + err.message;

    if (err.message.includes('登录已过期')) {
      setTimeout(() => {
        this.logout();
      }, 2000);
    }
  }
},

    // ========== 修复closePreview方法，清理blob URL ==========
closePreview() {
  // 清理blob URL
  if (this.previewUrl && this.previewUrl.startsWith('blob:')) {
    URL.revokeObjectURL(this.previewUrl);
  }

  // 对于会话URL，无需特殊清理（会自动过期）
  if (this.previewUrl && this.previewUrl.includes('/api/preview-session/')) {
    console.log('关闭PDF预览会话');
  }

  this.showPreview = false;
  this.previewUrl = '';
  this.previewingFile = null;
  this.previewType = '';
  this.textContent = '';
},

    // ========== 用户管理 ==========
    async loadUserList() {
      try {
        const res = await axios.get('/api/users');
        this.userList = res.data;
      } catch (e) {
        alert('获取用户列表失败');
      }
    },
    async setAdmin(u, flag) {
      try {
        const res = await axios.patch(`/api/users/${u.id}`, { is_admin: flag });
        if (res.data.success) u.is_admin = flag ? 1 : 0;
      } catch (e) {
        alert(e?.response?.data?.error || '操作失败');
      }
    },
    async setActive(u, flag) {
      try {
        const res = await axios.patch(`/api/users/${u.id}`, { is_active: flag });
        if (res.data.success) u.is_active = flag ? 1 : 0;
      } catch (e) {
        alert(e?.response?.data?.error || '操作失败');
      }
    },

    // ========== 面板导航 ==========


    // 获取可用盘符
    async fetchAvailableDrives() {
      try {
        const res = await axios.get('/api/drives');
        this.availableDrives = res.data;
        if (this.availableDrives.length > 0) {
          this.currentDrive = this.availableDrives[0].drive;
        }
      } catch (err) {
        console.error('获取盘符失败:', err);
      }
    },

    // 切换盘符
    switchDrive(drive) {
      this.currentDrive = drive;
      this.currentPath = '/';
      this.loadFileList('/');
    },

    // Samba 重启
    async restartSamba() {
      try {
        const res = await axios.post('/api/restart_samba');
        this.sambaMessage = res.data.message || '操作成功';
      } catch (err) {
        this.sambaMessage = err.response?.data?.error || '操作失败';
      }
    },


    // 工具方法
    formatUptime(seconds) {
      if (!seconds) return '';
      const days = Math.floor(seconds / 86400);
      const hours = Math.floor((seconds % 86400) / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      let result = '';
      if (days > 0) result += days + '天';
      if (hours > 0) result += hours + '小时';
      result += minutes + '分钟';
      return result;
    },

    // ========== OnlyOffice ==========
    async createOnlyOfficeDocument(filePath, fileName) {
      try {
        const response = await axios.post('/api/onlyoffice/documents', {
          file_name: fileName,
          file_path: filePath,
          file_type: '.docx'
        });

        if (response.data.success) {
          return response.data.document.id;
        } else {
          throw new Error(response.data.error || '创建文档失败');
        }
      } catch (error) {
        console.error('创建 OnlyOffice 文档失败:', error);
        throw error;
      }
    },

    isCollabEditable(item) {
      // 支持的文档类型扩展名
      const textExts = ['.txt', '.md', '.json', '.csv', '.py', '.js', '.html', '.css', '.log'];
      const officeExts = ['.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt'];

      const fileName = item.name.toLowerCase();
      return textExts.some(ext => fileName.endsWith(ext)) ||
             officeExts.some(ext => fileName.endsWith(ext));
    },

    async openCollabEdit(item) {
  try {
    const fileName = item.name.toLowerCase();
    const textExts = ['.txt', '.md', '.json', '.csv', '.py', '.js', '.html', '.css', '.log'];
    const officeExts = ['.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt'];

    // ✅ 构建完整路径
    const fullPath = this.buildFullPath(item.name);
    console.log('协作编辑请求路径:', fullPath); // 调试日志

    // 检查文件类型
    if (officeExts.some(ext => fileName.endsWith(ext))) {
      await this.openOfficeCollabEdit(item, fullPath);
    } else if (textExts.some(ext => fileName.endsWith(ext))) {
      await this.openTextCollabEdit(item, fullPath);
    } else {
      alert('不支持的文件类型');
    }
  } catch (error) {
    console.error('创建协作会话失败:', error);
    alert('创建协作会话失败: ' + (error.response?.data?.error || error.message));
  }
},

    // 打开Office文档协作编辑
    async openOfficeCollabEdit(item, fullPath) {
      try {
        // 首先尝试创建OnlyOffice文档记录
        const response = await axios.post('/api/onlyoffice/documents', {
          file_name: item.name,
          file_path: fullPath,
          file_type: '.' + item.name.split('.').pop()
        });

        if (response.data.success) {
          const docId = response.data.document.id;
          const onlyofficeUrl = `/onlyoffice-edit.html?doc_id=${docId}&mode=edit`;

          // 在新窗口中打开OnlyOffice编辑器
          window.open(onlyofficeUrl, '_blank');
        } else {
          // OnlyOffice服务不可用，降级为下载模式
          this.showOfficeDownloadOption(item, fullPath);
        }
      } catch (error) {
        console.error('打开 OnlyOffice 编辑器失败:', error);
        // OnlyOffice服务不可用，降级为下载模式
        this.showOfficeDownloadOption(item, fullPath);
      }
    },

    // 显示Office文档下载选项
    showOfficeDownloadOption(item, fullPath) {
      const message = `OnlyOffice 编辑器暂时不可用。\n\n文件：${item.name}\n\n您可以选择：\n1. 下载文件到本地编辑\n2. 稍后重试\n\n是否现在下载文件？`;

      if (confirm(message)) {
        this.downloadOfficeFile(item, fullPath);
      }
    },

    // 下载Office文件
    async downloadOfficeFile(item, fullPath) {
      try {
        const response = await fetch(`/api/download?path=${encodeURIComponent(fullPath)}`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });

        if (response.ok) {
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = item.name;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          window.URL.revokeObjectURL(url);

          alert('文件下载成功！您可以使用本地Office软件进行编辑。');
        } else {
          throw new Error(`下载失败: ${response.status}`);
        }
      } catch (error) {
        console.error('下载文件失败:', error);
        alert('下载文件失败: ' + error.message);
      }
    },

    // 打开文本文件协作编辑
    async openTextCollabEdit(item, fullPath) {
      try {
        const response = await axios.post('/api/collaboration/create', {
          file_path: fullPath,
          file_name: item.name,
          expire_hours: 24
        });

        if (response.data.success) {
          const session = response.data.session;
          const shareUrl = window.location.origin + session.share_url;

          // 显示分享链接
          if (confirm(`协作会话创建成功！\n\n分享链接：${shareUrl}\n\n是否复制链接到剪贴板？`)) {
            navigator.clipboard.writeText(shareUrl);
            alert('链接已复制到剪贴板！');
          }

          // 直接打开协作页面
          window.open(session.share_url, '_blank');
        } else {
          alert('创建协作会话失败: ' + response.data.error);
        }
      } catch (error) {
        console.error('创建文本协作会话失败:', error);
        alert('创建文本协作会话失败: ' + (error.response?.data?.error || error.message));
      }
    },

    // 协作分享弹窗
    openCollabShareDialog(item) {
      this.collabShareFile = item;
      this.collabSharePassword = '';
      this.collabShareExpire = 24;
      this.collabShareUrl = '';
      this.collabShareError = '';
      this.showCollabShareDialog = true;
    },

    async submitCollabShare() {
      try {
        const res = await axios.post('/api/collab/share', {
          file: this.collabShareFile.name,
          path: this.currentPath,
          password: this.collabSharePassword,
          expire: this.collabShareExpire
        });
        if (res.data.success) {
          this.collabShareUrl = window.location.origin + res.data.share_url + (this.collabSharePassword ? `&pw=${encodeURIComponent(this.collabSharePassword)}` : '');
        } else {
          this.collabShareError = res.data.error || '生成失败';
        }
      } catch (e) {
        this.collabShareError = '生成失败';
      }
    }
  },

  watch: {
    showUserAdmin(val) {
      if (val) this.loadUserList();
    }
  },

  mounted() {
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');
    if (token && userData) {
      try {
        axios.defaults.headers.common['Authorization'] = 'Bearer ' + token;
        this.user = JSON.parse(userData);
        this.loggedIn = true;
        this.loadMainPanel();
      } catch (e) {
        this.logout();
      }
    }
  },

  beforeUnmount() {
    this.stopSysTimer();
  }
});

app.mount('#app');