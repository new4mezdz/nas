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
      fileList: [],
      newDirName: '',
      uploadTargetDir: '/',
      allDirs: ['/'],
      uploadInfo: '',
       selectedFiles: [],

      // 文件操作
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
       // 分享
    shareDialogVisible: false,
    shareFile: null,
    shareExpire: 24,
    sharePassword: '',
    shareUrl: '',
        // 纠删码
         ecScheme: 'rs',
    k: 4,
    m: 2,
    selectedDisks: [],
    disks: []  // 后端获取磁盘信息
    }
  },
computed: {
  // 非纠删码磁盘列表
  nonECDiskList() {
    return this.disks.filter(d => !d.ec_scheme);
  },

  // 合并显示纠删码磁盘为一个逻辑卷
  ecDiskGroup() {
    const ecDisks = this.disks.filter(d => d.ec_scheme);
    if (ecDisks.length === 0) return null;

    const total = ecDisks.reduce((sum, d) => sum + d.total, 0);
    const used = ecDisks.reduce((sum, d) => sum + d.used, 0);
    const percent = Math.round((used / total) * 1000) / 10;

    return {
      total,
      used,
      percent,
      ec_scheme: ecDisks[0].ec_scheme // 默认用第一个的方案名
    };
  },

  // 文件是否全选
  allSelected() {
    return this.fileList.length > 0 && this.selectedFiles.length === this.fileList.length;
  }
},

  methods: {
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
        this.pwMsg = "两次输入的新密码不一致";
        return;
      }
      try {
        const res = await axios.patch('/api/change_password', {
          old_password: this.pwForm.old_password,
          new_password: this.pwForm.new_password
        });
        if (res.data && res.data.success) {
          this.pwMsg = "修改成功，请重新登录";
          setTimeout(() => {
            this.showChangePw = false;
            this.logout();
          }, 1200);
        } else {
          this.pwMsg = res.data.error || "修改失败";
        }
      } catch (e) {
        this.pwMsg = e.response?.data?.error || "修改失败";
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

    // ========== 系统/磁盘信息，动态刷新 ==========
    async fetchSystemInfo() {
      try {
        const res = await axios.get('/api/system');
        this.systemInfo = res.data;
      } catch (e) {
        this.logout();
      }
    },
    async fetchDiskInfo() {
      try {
        const res = await axios.get('/api/disk');
        this.disks = res.data;
      } catch (e) {}
    },
    startSysTimer() {
      this.stopSysTimer();
      this._sysTimer = setInterval(() => {
        if (this.loggedIn) this.fetchSystemInfo();
      }, 10000);
    },
    stopSysTimer() {
      if (this._sysTimer) clearInterval(this._sysTimer);
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

  goToFile(file) {
    this.showSearchDialog = false;
    alert(`✅ 搜索成功，正在定位文件 ${file.name}`);

    this.loadFileList(file.directory, () => {
      // ⏬ 高亮目标文件
      this.$nextTick(() => {
        const rows = document.querySelectorAll(".file-list tr");
        rows.forEach(row => {
          if (row.innerText.includes(file.name)) {
            row.scrollIntoView({ behavior: "smooth", block: "center" });
            row.classList.add("highlight");
            setTimeout(() => row.classList.remove("highlight"), 2000);
          }
        });
      });
    });
  },

  loadFileList(path, callback) {
    const token = localStorage.getItem("token");
    fetch(`/api/list?path=${encodeURIComponent(path)}`, {
      headers: { "Authorization": `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          this.fileList = data.items; // 假设你已经绑定了这个 fileList
          this.currentPath = path;
          if (callback) callback();
        } else {
          alert("❌ 加载失败：" + (data.error || ""));
        }
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
    this.loadFiles(newPath);
  },

    goECVolume() {
    this.loadFiles('/ec_volume');  // 这个路径在后端中会映射为第一个 EC 磁盘
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
      await Promise.all(this.selectedFiles.map(name => {
        return axios.post('/api/delete', { path: this.currentPath.replace(/\/$/, '') + '/' + name });
      }));
      this.selectedFiles = [];
      this.loadFiles(this.currentPath);
    },
    onSearchInput() {
  if (this.searchTimer) clearTimeout(this.searchTimer);
  this.searchTimer = setTimeout(() => {
    this.loadFiles(this.currentPath);
  }, 300);
},

    uploadFile() {
  const file = this.$refs.uploadFileInput.files[0];
  if (!file) {
    this.uploadInfo = "请先选择文件";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("path", this.currentPath);  // ✅ 传递当前路径

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
        this.loadFiles();  // 重新加载文件列表
      } else {
        this.uploadInfo = data.error || "上传失败";
      }
    })
    .catch((err) => {
      this.uploadInfo = "上传出错：" + err;
    });
},

    goDisk(mountPath) {
  // 将 Windows 的反斜杠路径转换为 URL 兼容形式
  const path = mountPath.replace(/\\/g, '/');
  this.loadFiles(path);
},
    goParent() {
  if (this.currentPath === '/' || this.currentPath === '') return;

  const parts = this.currentPath.split('/').filter(p => p);
  parts.pop();  // 删除最后一级目录名
  const parentPath = '/' + parts.join('/');
  this.loadFiles(parentPath || '/');
},
    fileSelected() {
      this.uploadInfo = '';
    },
    async mkdir() {
      if (!this.newDirName) return;
      try {
        const res = await axios.post('/api/mkdir', { parent: this.currentPath, name: this.newDirName });
        if (res.data.success) {
          this.loadFiles(this.currentPath);
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
        const res = await axios.post('/api/delete', { path: this.currentPath.replace(/\/$/, '') + '/' + item.name });
        if (res.data.success) {
          this.loadFiles(this.currentPath);
        }
      } catch (e) {
        alert(e?.response?.data?.error || "删除失败");
      }
    },
    startRename(item) {
      this.renaming = item.name;
      this.renameTo = item.name;
    },
    async submitRename(item) {
      if (!this.renameTo || this.renameTo === item.name) {
        this.cancelRename(); return;
      }
      try {
        const res = await axios.post('/api/rename', {
          path: this.currentPath.replace(/\/$/, '') + '/' + item.name,
          new_name: this.renameTo
        });
        if (res.data.success) {
          this.loadFiles(this.currentPath);
          this.cancelRename();
        }
      } catch (e) {
        alert(e?.response?.data?.error || '重命名失败');
      }
    },
    cancelRename() {
      this.renaming = null;
      this.renameTo = '';
    },
    downloadFile(item) {
      window.open('/api/download?path=' + encodeURIComponent(this.currentPath.replace(/\/$/, '') + '/' + item.name));
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
      const res = await axios.post('/api/share', {
        file_path: this.currentPath.replace(/\/$/, '') + '/' + this.shareFile.name,
        expire_hours: this.shareExpire,
        password: this.sharePassword
      });
      if (res.data.success) {
        // 这里假设你服务端和前端在同一个域名/端口
        this.shareUrl = window.location.origin + res.data.share_url;
      }
    } catch (e) {
      alert(e?.response?.data?.error || "分享失败");
    }
  },
      // ========== 纠删码 ==========
      async applyECScheme() {
    try {
      const res = await axios.post('/api/ec_config', {
        scheme: this.ecScheme,
        k: this.k,
        m: this.m,
        disks: this.selectedDisks
      });
      alert(res.data.message || "配置已应用");
    } catch (e) {
      alert(e.response?.data?.error || "配置失败");
    }
  },

      async applyECScheme() {
  try {
    const payload = {
      scheme: this.ecScheme,
      disks: this.selectedDisks
    };

    if (this.ecScheme) {
      payload.k = this.k;
      payload.m = this.m;
    }

    const res = await axios.post('/api/ec_config', payload);
    alert(res.data.message || "配置已应用");
  } catch (e) {
    alert(e.response?.data?.error || "配置失败");
  }
},

 // ========== 文件预览 ==========
      isImage(file) {
    return /\.(jpg|jpeg|png|gif|bmp|webp)$/i.test(file.name);
  },
  isVideo(file) {
    return /\.(mp4|webm|ogg|mov|avi)$/i.test(file.name);
  },
  isAudio(file) {
    return /\.(mp3|wav|ogg|m4a)$/i.test(file.name);
  },
  previewFile(file) {
    this.previewingFile = file;
    this.previewUrl = `/api/preview?path=${encodeURIComponent(this.currentPath.replace(/\/$/, '') + '/' + file.name)}`;
    this.previewType = this.isImage(file) ? 'image' : (this.isVideo(file) ? 'video' : (this.isAudio(file) ? 'audio' : 'other'));
    this.showPreview = true;
  },
  closePreview() {
    this.showPreview = false;
    this.previewUrl = '';
    this.previewingFile = null;
    this.previewType = '';
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
    async loadMainPanel() {
      await Promise.all([
        this.fetchSystemInfo(),
        this.fetchDiskInfo(),
        this.loadFiles("/")
      ]);
      this.startSysTimer();
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
app.mount('#app')
