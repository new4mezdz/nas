// desktop_helpContent.js - 客户端帮助文档内容配置
const helpContent = {
    // 目录
    chapters: [
        { id: 'quickstart', title: '快速入门', icon: '🚀' },
        { id: 'files', title: '文件管理', icon: '📁' },
        { id: 'pool', title: '空间池', icon: '📦' },
        { id: 'disk', title: '磁盘管理', icon: '💿' },
        { id: 'encryption', title: '磁盘加密', icon: '🔐' },
        { id: 'system', title: '系统信息', icon: '📊' },
        { id: 'settings', title: '个性化设置', icon: '⚙️' },
        { id: 'faq', title: '常见问题', icon: '💡' }
    ],

    // 各章节内容
    sections: {
        // ========== 快速入门 ==========
        quickstart: {
            title: '快速入门',
            blocks: [
                { type: 'text', content: '欢迎使用 NAS Web Desktop！这是您的个人网络存储空间，可以像操作本地电脑一样管理您的文件。' },
                { type: 'image', src: '/static/images/help/desktop-overview.png', caption: '桌面主界面' },

                { type: 'heading', content: '桌面布局' },
                { type: 'list', items: [
                    { label: '桌面图标', desc: '双击图标打开对应的应用程序' },
                    { label: '任务栏', desc: '底部任务栏显示已打开的窗口，点击可切换' },
                    { label: '开始菜单', desc: '点击左下角按钮打开开始菜单' },
                    { label: '系统时间', desc: '右下角显示当前时间' }
                ]},

                { type: 'heading', content: '快速搜索' },
                { type: 'text', content: '点击任务栏的搜索图标或使用快捷键，可以快速搜索应用和文件。' },
                { type: 'list', items: [
                    { label: '搜索应用', desc: '输入应用名称如"文件"、"磁盘"快速打开' },
                    { label: '搜索文件', desc: '输入文件名关键词，全盘搜索文件' }
                ]},
                { type: 'tip', content: '使用上下箭头键选择搜索结果，回车键确认。' }
            ]
        },

        // ========== 文件管理 ==========
        files: {
            title: '文件管理',
            blocks: [
                { type: 'text', content: '文件管理器是您管理存储文件的主要工具，支持上传、下载、复制、移动、删除等操作。' },
                { type: 'image', src: '/static/images/help/file-manager.png', caption: '文件管理器界面' },

                { type: 'heading', content: '界面说明' },
                { type: 'list', items: [
                    { label: '左侧边栏', desc: '显示所有可用的存储位置（磁盘、空间池、逻辑卷）' },
                    { label: '文件列表', desc: '显示当前目录的文件和文件夹' },
                    { label: '工具栏', desc: '提供上传、新建文件夹、视图切换等功能' },
                    { label: '路径栏', desc: '显示当前位置，可点击快速跳转' }
                ]},

                { type: 'heading', content: '上传文件' },
                { type: 'steps', items: [
                    { title: '点击上传按钮', text: '在工具栏点击"上传"按钮' },
                    { title: '选择文件', text: '在弹出的对话框中选择要上传的文件' },
                    { title: '等待上传', text: '文件将自动上传，可在进度条查看状态' }
                ]},
                { type: 'tip', content: '也可以直接将文件拖拽到文件列表区域进行上传。' },

                { type: 'heading', content: '文件操作' },
                { type: 'text', content: '右键点击文件可打开操作菜单：' },
                { type: 'list', items: [
                    { label: '下载', desc: '将文件下载到本地电脑' },
                    { label: '复制', desc: '复制文件到剪贴板' },
                    { label: '剪切', desc: '剪切文件（移动）' },
                    { label: '粘贴', desc: '将剪贴板中的文件粘贴到当前目录' },
                    { label: '重命名', desc: '修改文件或文件夹名称' },
                    { label: '删除', desc: '删除选中的文件' }
                ]},
                { type: 'warning', content: '删除操作不可恢复，请谨慎操作！' },

                { type: 'heading', content: '批量操作' },
                { type: 'text', content: '按住 Ctrl 键点击可多选文件，然后进行批量下载、复制、删除等操作。' },

                { type: 'heading', content: '视图模式' },
                { type: 'list', items: [
                    { label: '列表视图', desc: '显示详细信息，包括大小、修改时间等' },
                    { label: '图标视图', desc: '以大图标形式显示，适合浏览图片' }
                ]}
            ]
        },

        // ========== 空间池 ==========
        pool: {
            title: '空间池',
            blocks: [
                { type: 'text', content: '空间池可以将多个物理磁盘合并为一个统一的存储空间，并通过"逻辑卷"进行分类管理。' },
                { type: 'image', src: '/static/images/help/pool-overview.png', caption: '空间池管理界面' },

                { type: 'heading', content: '基本概念' },
                { type: 'list', items: [
                    { label: '空间池', desc: '由多个物理磁盘组成的虚拟存储空间' },
                    { label: '逻辑卷', desc: '空间池中的分类目录，如"电影"、"文档"、"音乐"' },
                    { label: '分配策略', desc: '决定文件存储到哪个物理磁盘的规则' }
                ]},

                { type: 'heading', content: '创建空间池' },
                { type: 'steps', items: [
                    { title: '打开空间池应用', text: '双击桌面的"空间池"图标' },
                    { title: '点击创建', text: '点击"创建存储池"按钮' },
                    { title: '选择磁盘', text: '勾选要加入池的磁盘' },
                    { title: '确认创建', text: '点击确定完成创建' }
                ]},
                { type: 'warning', content: '创建空间池不会删除磁盘上的现有数据，但建议先备份重要文件。' },

                { type: 'heading', content: '创建逻辑卷' },
                { type: 'text', content: '空间池创建后，需要创建逻辑卷才能存储文件。' },
                { type: 'list', items: [
                    { label: '卷标识', desc: '英文名称，如 movies、documents' },
                    { label: '显示名称', desc: '中文名称，如 电影、文档' },
                    { label: '图标', desc: '选择一个代表性图标' },
                    { label: '分配策略', desc: '选择文件分配到磁盘的策略' }
                ]},

                { type: 'heading', content: '分配策略说明' },
                { type: 'list', items: [
                    { label: '最大剩余空间优先', desc: '优先使用剩余空间最大的磁盘，适合大文件' },
                    { label: '轮询分配', desc: '依次使用每个磁盘，均衡写入' },
                    { label: '按剩余比例加权', desc: '根据各磁盘剩余空间比例分配' }
                ]},

                { type: 'heading', content: '数据平衡' },
                { type: 'text', content: '当各磁盘使用率不均衡时，可以执行数据平衡操作，将文件在磁盘间重新分配。' },
                { type: 'tip', content: '数据平衡可能需要较长时间，建议在空闲时执行。' }
            ]
        },

        // ========== 磁盘管理 ==========
        disk: {
            title: '磁盘管理',
            blocks: [
                { type: 'text', content: '磁盘管理显示所有可用的物理磁盘信息，包括容量、使用情况等。' },
                { type: 'image', src: '/static/images/help/disk-manager.png', caption: '磁盘管理界面' },

                { type: 'heading', content: '磁盘信息' },
                { type: 'list', items: [
                    { label: '盘符', desc: '磁盘的标识符，如 C:、D:' },
                    { label: '总容量', desc: '磁盘的总存储空间' },
                    { label: '已用空间', desc: '已使用的存储空间' },
                    { label: '可用空间', desc: '剩余可用的存储空间' },
                    { label: '使用率', desc: '已用空间占总容量的百分比' }
                ]},

                { type: 'heading', content: '磁盘状态' },
                { type: 'list', items: [
                    { label: '🟢 正常', desc: '磁盘运行正常' },
                    { label: '🟡 警告', desc: '磁盘空间不足（使用率超过80%）' },
                    { label: '🔴 危险', desc: '磁盘空间严重不足（使用率超过95%）' }
                ]},
                { type: 'tip', content: '建议保持磁盘使用率在80%以下，以确保系统正常运行。' }
            ]
        },

        // ========== 磁盘加密 ==========
        encryption: {
            title: '磁盘加密',
            blocks: [
                { type: 'text', content: '磁盘加密功能可以保护您的数据安全，即使磁盘被物理盗取也无法读取数据。' },
                { type: 'image', src: '/static/images/help/encryption.png', caption: '磁盘加密管理' },

                { type: 'heading', content: '加密状态' },
                { type: 'list', items: [
                    { label: '未加密', desc: '磁盘未启用加密' },
                    { label: '已加密（已解锁）', desc: '加密磁盘当前已解锁，可正常访问' },
                    { label: '已加密（已锁定）', desc: '加密磁盘已锁定，需要密码解锁' }
                ]},

                { type: 'heading', content: '加密磁盘' },
                { type: 'steps', items: [
                    { title: '选择磁盘', text: '在磁盘列表中选择要加密的磁盘' },
                    { title: '点击加密', text: '点击"加密"按钮' },
                    { title: '设置密码', text: '输入加密密码（请牢记！）' },
                    { title: '确认加密', text: '等待加密完成' }
                ]},
                { type: 'warning', content: '加密密码一旦遗忘将无法恢复，数据将永久丢失！请务必牢记密码！' },

                { type: 'heading', content: '解锁磁盘' },
                { type: 'text', content: '已锁定的加密磁盘需要输入正确密码才能解锁访问。' },

                { type: 'heading', content: '锁定磁盘' },
                { type: 'text', content: '可以随时锁定已解锁的加密磁盘，锁定后需要密码才能再次访问。' },
                { type: 'tip', content: '离开时锁定加密磁盘可以提高数据安全性。' }
            ]
        },

        // ========== 系统信息 ==========
        system: {
            title: '系统信息',
            blocks: [
                { type: 'text', content: '系统信息显示当前NAS节点的运行状态和资源使用情况。' },
                { type: 'image', src: '/static/images/help/system-info.png', caption: '系统信息界面' },

                { type: 'heading', content: '监控指标' },
                { type: 'list', items: [
                    { label: 'CPU使用率', desc: '处理器当前负载' },
                    { label: '内存使用', desc: '已用内存和总内存' },
                    { label: '磁盘空间', desc: '各磁盘的存储使用情况' },
                    { label: '网络状态', desc: '网络连接信息' },
                    { label: '系统运行时间', desc: '系统自上次启动以来的运行时长' }
                ]},

                { type: 'heading', content: '系统信息' },
                { type: 'list', items: [
                    { label: '主机名', desc: 'NAS节点的名称' },
                    { label: '操作系统', desc: '系统版本信息' },
                    { label: 'IP地址', desc: '节点的网络地址' }
                ]}
            ]
        },

        // ========== 个性化设置 ==========
        settings: {
            title: '个性化设置',
            blocks: [
                { type: 'text', content: '您可以根据个人喜好自定义桌面外观和使用习惯。' },

                { type: 'heading', content: '桌面背景' },
                { type: 'text', content: '点击开始菜单中的"桌面背景"，或右键点击桌面选择"更换背景"。' },
                { type: 'list', items: [
                    { label: '预设背景', desc: '选择系统提供的渐变色背景' },
                    { label: '自定义图片', desc: '上传自己的图片作为背景' },
                    { label: '网络图片', desc: '输入图片URL使用网络图片' }
                ]},
                { type: 'image', src: '/static/images/help/bg-settings.png', caption: '背景设置' },

                { type: 'heading', content: '个人设置' },
                { type: 'text', content: '在开始菜单中打开"个人设置"，可以修改个人信息。' },
                { type: 'list', items: [
                    { label: '头像', desc: '上传个人头像' },
                    { label: '密码', desc: '修改登录密码' }
                ]}
            ]
        },

        // ========== 常见问题 ==========
        faq: {
            title: '常见问题',
            blocks: [
                { type: 'heading', content: '文件上传失败怎么办？' },
                { type: 'text', content: '请检查以下几点：' },
                { type: 'list', items: [
                    { label: '1', desc: '检查网络连接是否正常' },
                    { label: '2', desc: '确认目标磁盘有足够的剩余空间' },
                    { label: '3', desc: '检查文件名是否包含特殊字符' },
                    { label: '4', desc: '尝试刷新页面后重新上传' }
                ]},

                { type: 'heading', content: '为什么有些操作按钮是灰色的？' },
                { type: 'text', content: '灰色按钮表示您当前没有执行该操作的权限。权限由管理员在管理端配置。' },
                { type: 'list', items: [
                    { label: '只读权限', desc: '只能查看和下载文件' },
                    { label: '读写权限', desc: '可以上传、复制、移动文件' },
                    { label: '完全控制', desc: '可以执行所有操作包括删除' }
                ]},

                { type: 'heading', content: '忘记加密密码怎么办？' },
                { type: 'text', content: '很抱歉，加密密码无法找回或重置。如果遗忘密码，磁盘数据将无法访问。' },
                { type: 'warning', content: '请务必将加密密码记录在安全的地方！' },

                { type: 'heading', content: '空间池和普通磁盘有什么区别？' },
                { type: 'text', content: '空间池是多个磁盘的组合：' },
                { type: 'list', items: [
                    { label: '普通磁盘', desc: '单个物理磁盘，容量固定' },
                    { label: '空间池', desc: '多个磁盘组合，可扩展容量，文件自动分配' }
                ]},

                { type: 'heading', content: '如何退出登录？' },
                { type: 'text', content: '点击开始菜单，然后点击"退出登录"按钮即可。' },

                { type: 'heading', content: '支持哪些文件格式预览？' },
                { type: 'text', content: '目前支持以下格式的在线预览：' },
                { type: 'list', items: [
                    { label: '图片', desc: 'JPG、PNG、GIF、WebP 等' },
                    { label: '视频', desc: 'MP4、WebM 等浏览器支持的格式' },
                    { label: '音频', desc: 'MP3、WAV 等' },
                    { label: '文本', desc: 'TXT、MD、代码文件等' }
                ]},
                { type: 'tip', content: '不支持预览的文件可以下载到本地查看。' }
            ]
        }
    }
};