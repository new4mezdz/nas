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

      // 预览
    showPreview: false,
    previewingFile: null,
    previewUrl: '',
    previewType: '',
    }
  },
computed: {
  allSelected() {
    return this.fileList.length && this.selectedFiles.length === this.fileList.length;
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
    async loadFiles(path = "/") {
      // 获取文件列表并清空多选
      const res = await axios.get('/api/files', { params: { path } });
      this.currentPath = res.data.current;
      this.fileList = res.data.items;
      this.selectedFiles = [];
    },
    goDir(dirname) {
      let path = this.currentPath.endsWith('/') ? this.currentPath : this.currentPath + '/';
      this.loadFiles(path + dirname);
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
    async uploadFile() {
      const files = this.$refs.uploadFileInput.files;
      if (!files || !files[0]) return;
      const formData = new FormData();
      formData.append('file', files[0]);
      formData.append('path', this.uploadTargetDir || this.currentPath);
      try {
        const res = await axios.post('/api/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        this.uploadInfo = '上传成功';
        this.loadFiles(this.currentPath);
      } catch (e) {
        this.uploadInfo = '上传失败';
      }
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
