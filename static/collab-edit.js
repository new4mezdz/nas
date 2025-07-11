const Y = window.Y;
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
  fetch(`/api/collab/load?file=${encodeURIComponent(file)}&path=${encodeURIComponent(path)}`)
    .then(res => res.json())
    .then(data => {
      let initialContent = '';
      if (data.success && data.content) {
        initialContent = data.content;
      }
      startCollab(file, path, token, initialContent);
    });
}

function startCollab(file, path, token, initialContent) {
  document.getElementById('fileName').textContent = decodeURIComponent(file || '');
  const roomName = token || encodeURIComponent((path || '') + '/' + (file || ''));
  // 1. 创建Yjs文档
  theYdoc = new Y.Doc();
  // 2. 连接WebSocket服务器（roomName为协作房间名/文档ID）
  const provider = new window.Y.WebsocketProvider('ws://localhost:1234', roomName, theYdoc);
  // 3. 绑定到Quill
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
  // 4. 只在本地初始化时设置内容（避免协作覆盖）
  if (initialContent) {
    quill.setContents(quill.clipboard.convert(initialContent));
  }
  // 5. 绑定协作
  const ytext = theYdoc.getText('quill');
  const binding = new window.Y.QuillBinding(ytext, quill, provider.awareness);

  // 在线用户显示
  document.getElementById('userCount').textContent = 1;
  provider.awareness.on('change', () => {
    const states = Array.from(provider.awareness.getStates().values());
    document.getElementById('userCount').textContent = states.length;
  });

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