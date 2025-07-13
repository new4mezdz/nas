// 解析URL参数
function getQueryParam(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

const file = getQueryParam('file');
const path = getQueryParam('path');
const token = getQueryParam('token');
const pwFromUrl = getQueryParam('pw');

let quill = null; // 全局变量

function loadFileContentAndStartCollab(file, path, token) {
  console.log('开始加载文件内容:', file, path);
  fetch(`/api/collab/load?file=${encodeURIComponent(file)}&path=${encodeURIComponent(path)}`)
    .then(res => {
      console.log('API响应状态:', res.status, res.statusText);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      return res.text(); // 先获取文本内容
    })
    .then(text => {
      console.log('API响应文本长度:', text.length);
      console.log('API响应文本前100字符:', text.substring(0, 100));
      
      try {
        const data = JSON.parse(text);
        console.log('JSON解析成功:', data);
        
        let initialContent = '';
        if (data.success && data.content) {
          initialContent = data.content;
          console.log('文件内容长度:', initialContent.length);
        } else {
          console.error('API返回失败:', data.error);
          alert('加载文件失败: ' + (data.error || '未知错误'));
          return;
        }
        startCollab(file, path, token, initialContent);
      } catch (jsonError) {
        console.error('JSON解析失败:', jsonError);
        console.error('响应文本:', text);
        alert('解析文件内容失败: ' + jsonError.message);
      }
    })
    .catch(error => {
      console.error('加载文件失败:', error);
      alert('加载文件失败: ' + error.message);
    });
}

function startCollab(file, path, token, initialContent) {
  document.getElementById('fileName').textContent = decodeURIComponent(file || '');
  
  // 使用纯Quill编辑器，不依赖Yjs和WebSocket
  console.log('使用本地编辑模式');
  
  // 初始化Quill编辑器
  quill = new Quill('#editor', {
    theme: 'snow',
    modules: { toolbar: [
      [{ header: [1, 2, false] }],
      ['bold', 'italic', 'underline'],
      ['link', 'blockquote', 'code-block', 'image'],
      [{ list: 'ordered' }, { list: 'bullet' }],
      [{ 'align': [] }],
      ['clean']
    ] }
  });
  window.quill = quill;
  
  // 设置初始内容
  if (initialContent) {
    quill.setContents(quill.clipboard.convert(initialContent));
  }
  
  // 本地编辑模式
  document.getElementById('userCount').textContent = '本地编辑';

  // 状态栏
  const statusBar = document.getElementById('statusBar');
  function setStatus(msg, ok = true) {
    statusBar.textContent = msg;
    statusBar.style.color = ok ? '#16a34a' : '#dc2626';
    setTimeout(() => { statusBar.textContent = ''; }, 3000);
  }

  // 手动保存
  const saveBtn = document.getElementById('saveBtn');
  saveBtn.onclick = async function() {
    await saveToBackend();
  };

  // 定时自动保存
  setInterval(saveToBackend, 10000); // 每10秒自动保存

  async function saveToBackend() {
    const content = quill.root.innerHTML;
    try {
      const res = await fetch('/api/collab/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file, path, content })
      });
      const data = await res.json();
      if (data.success) setStatus('保存成功', true);
      else setStatus(data.error || '保存失败', false);
    } catch (e) {
      setStatus('保存失败', false);
    }
  }
}

if (token) {
  // 协作分享模式，需校验token和密码
  document.getElementById('authBox').style.display = '';
  document.getElementById('editor').style.display = 'none';
  document.getElementById('toolbar').style.display = 'none';
  document.getElementById('saveBtn').style.display = 'none';
  document.getElementById('fileName').textContent = '';
  let validated = false;
  async function tryValidate(pw) {
    const res = await fetch('/api/collab/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password: pw })
    });
    const data = await res.json();
    if (data.success) {
      validated = true;
      document.getElementById('authBox').style.display = 'none';
      document.getElementById('editor').style.display = '';
      document.getElementById('toolbar').style.display = '';
      document.getElementById('saveBtn').style.display = '';
      document.getElementById('fileName').textContent = data.file;
      // 加载内容并初始化协作
      loadFileContentAndStartCollab(data.file, data.path, token);
    } else {
      document.getElementById('pwError').textContent = data.error || '校验失败';
    }
  }
  document.getElementById('pwBtn').onclick = () => {
    tryValidate(document.getElementById('pwInput').value);
  };
  if (pwFromUrl) {
    tryValidate(pwFromUrl);
  }
} else {
  // 普通模式
  loadFileContentAndStartCollab(file, path, null);
} 