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
      textContent: '',
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
    disks: [],  // 后端获取磁盘信息


      
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
    // 添加盘符前缀
    const fullPath = this.currentDrive + path.replace(/^\//, '');
    
    fetch(`/api/list?path=${encodeURIComponent(fullPath)}`, {
      headers: { "Authorization": `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          this.fileList = data.items;
          this.currentPath = path;
          
          // 更新用户当前目录到后端
          this.updateCurrentDirectory(path);
          
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
    this.loadFileList(newPath); // ✅ 正确的
  },

    goECVolume() {
     this.loadFileList('/ec_volume');  // 这个路径在后端中会映射为第一个 EC 磁盘
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
async uploadDraggedFiles() {
  if (!this.uploadFiles.length) return;

  const path = this.currentPath;
  const token = localStorage.getItem("token");

  for (const file of this.uploadFiles) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("path", path);

    try {
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
        this.loadFileList(this.currentPath); // ✅
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
  this.loadFileList(path);  // ✅ 正确
},
    goParent() {
  if (this.currentPath === '/' || this.currentPath === '') return;

  const parts = this.currentPath.split('/').filter(p => p);
  parts.pop();  // 删除最后一级目录名
  const parentPath = '/' + parts.join('/');
 this.loadFileList(parentPath || '/'); // ✅
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
        const res = await axios.post('/api/delete', { path: this.currentPath.replace(/\/$/, '') + '/' + item.name });
        if (res.data.success) {
          this.loadFileList(this.currentPath);
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
          this.loadFileList(this.currentPath);
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
      const token = localStorage.getItem('token');
      // 构建绝对路径：当前盘符 + 当前路径 + 文件名
      const fullPath = this.currentDrive + this.currentPath.replace(/^\//, '') + '/' + item.name;
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

  // 1. 构建完整路径：当前盘符 + 当前路径 + 文件名
  const fullPath = this.currentDrive + this.currentPath.replace(/^\//, '') + '/' + file.name;
  const baseApi = `/api/preview?path=${encodeURIComponent(fullPath)}`;
  const token = localStorage.getItem('token');

  // 2. 文本类文件：用 fetchTextContent 读取纯文本
  if (this.isText(file)) {
    this.previewType = 'text';
    this.fetchTextContent(baseApi);  // fetchTextContent 内部会用 axios 带上 header
    this.showPreview = true;
    return;
  }

  // 3. PDF 特例：iframe 预览，token 拼接到 URL 参数
  if (this.isPdf(file)) {
    this.previewUrl = `${baseApi}&token=${encodeURIComponent(token)}#toolbar=0`;
    this.previewType = 'pdf';
    this.showPreview = true;
    return;
  }

  // 4. DOCX 文件：使用本地 OnlyOffice 预览
  if (this.isDocx(file)) {
    // 先创建 OnlyOffice 文档记录，然后跳转到编辑页面
    this.createOnlyOfficeDocument(fullPath, file.name).then(docId => {
      const onlyofficeUrl = `/onlyoffice-edit.html?doc_id=${docId}&mode=view`;
      window.open(onlyofficeUrl, '_blank');
    }).catch(err => {
      alert("创建 OnlyOffice 文档失败：" + (err.response?.data?.error || '网络错误'));
      console.error("❌ OnlyOffice 创建失败:", err);
    });
    return;
  }

  // 5. 其他图片 / 音频 / 视频 → 使用 blob 显示 + 带 token 的 header
  axios.get(baseApi, {
    responseType: 'blob',
    headers: {
      Authorization: 'Bearer ' + token
    }
  }).then(res => {
    this.previewUrl = URL.createObjectURL(res.data);

    if (this.isImage(file)) this.previewType = 'image';
    else if (this.isVideo(file)) this.previewType = 'video';
    else if (this.isAudio(file)) this.previewType = 'audio';
    else this.previewType = 'other';

    this.showPreview = true;
  }).catch(err => {
    alert("预览失败：" + (err.response?.data?.error || '网络错误'));
    console.error("❌ 预览失败:", err);
  });
},


    fetchTextContent(url) {
  fetch(url, { headers: { Authorization: "Bearer " + localStorage.getItem("token") } })
    .then(res => res.text())
    .then(content => {
      this.textContent = content;
    })
    .catch(err => {
      this.textContent = '⚠️ 加载失败: ' + err.message;
    });
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
        this.fetchAvailableDrives(),
        this.loadFileList("/")
      ]);
      this.startSysTimer();
    },

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

    // ========== 文档协作 ==========

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
        
        // 构建完整路径：当前盘符 + 当前路径 + 文件名
        const fullPath = this.currentDrive + this.currentPath.replace(/^\//, '') + '/' + item.name;
        console.log('创建协作会话，文件路径:', fullPath);
        
        // 检查文件类型
        if (officeExts.some(ext => fileName.endsWith(ext))) {
          // Office文档：使用OnlyOffice协作编辑
          await this.openOfficeCollabEdit(item, fullPath);
        } else if (textExts.some(ext => fileName.endsWith(ext))) {
          // 文本文件：使用文本协作编辑
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
    },
  },
  watch: {
    showUserAdmin(val) {
      if (val) this.loadUserList();
    },

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
