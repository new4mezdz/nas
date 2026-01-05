// desktop_helpContent.js - 客户端帮助文档内容配置
const helpContent = {
    // 目录
    chapters: [
        { id: 'quickstart', title: '快速入门', icon: '🚀' },
        { id: 'files', title: '文件管理', icon: '📁' },
        { id: 'pool', title: '空间池', icon: '📦' },
        { id: 'disk', title: '磁盘管理', icon: '💿' },
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
                // 修改：desktop-main.png -> desktop-overview.png
                { type: 'image', src: '/images/help/desktop-overview.png', caption: '桌面主界面' },

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
                    { label: '搜索文件', desc: '输入文件名关键词，全盘搜索文件' },
                    // 修改：2.png -> desktop-search-bar.png
                    { type: 'image', src: '/images/help/desktop-search-bar.png', caption: '顶部抽屉搜索栏' },
                ]},
                { type: 'tip', content: '使用上下箭头键选择搜索结果，回车键确认。' }
            ]
        },

        // ========== 文件管理 ==========
        files: {
            title: '文件管理',
            blocks: [
                { type: 'text', content: '文件管理器是您管理存储文件的主要工具，支持上传、下载、复制、移动、删除、分享以及在线协作等高级功能。' },
                // 修改：3.png -> files-manager-main.png
                { type: 'image', src: '/images/help/files-manager-main.png', caption: '文件管理器界面' },

                { type: 'heading', content: '界面布局' },
                { type: 'list', items: [
                    { label: '左侧边栏', desc: '显示物理磁盘、空间池、逻辑卷及“纠删码卷”等存储位置。' },
                    { label: '工具栏', desc: '提供上传、新建、重命名、删除、剪切/复制/粘贴及搜索功能。' },
                    { label: '视图切换', desc: '位于工具栏右侧，可快速切换列表或网格显示模式。' }
                ]},

                { type: 'heading', content: '视图模式切换' },
                { type: 'text', content: '您可以根据需要随时切换文件的呈现方式：' },
                { type: 'list', items: [
                    { label: '📋 列表视图', desc: '显示文件名、大小、修改时间等详细元数据，适合精确查找。' },
                    { label: '⊞ 网格视图', desc: '以大图标形式展示，方便快速预览图片或多媒体文件。' }
                ]},

                { type: 'heading', content: '文件预览功能' },
                { type: 'text', content: '系统集成了强大的多媒体预览引擎，支持以下格式的直接查看：' },
                { type: 'list', items: [
                    { label: '🖼️ 图片', desc: '支持 JPG, PNG, GIF, WebP 等主流图像格式预览。' },
                    { label: '🎬 视频', desc: '支持 MP4, WebM 等浏览器原生支持的视频格式播放。' },
                    { label: '🎵 音频', desc: '支持 MP3, WAV 等音频文件在线试听。' },
                    { label: '📄 文档', desc: '支持 PDF 格式文件的在线阅读。' },
                    { label: '📝 文本', desc: '支持 TXT,代码文件等纯文本格式的查看。' }
                ]},

                { type: 'heading', content: '在线文档协作' },
                { type: 'text', content: '系统集成了 Univer 在线编辑器，支持无需下载即可直接编辑文档。' },
                { type: 'tip', content: '双击支持的表格或文档文件，系统将自动打开在线编辑窗口，支持实时保存。' },
                // 修改：4.png -> files-editor-univer.png
                { type: 'image', src: '/images/help/files-editor-univer.png', caption: 'Univer 在线文档编辑界面' },

                { type: 'heading', content: '文件分享链接' },
                { type: 'text', content: '您可以为文件创建外链分享，系统将生成唯一的访问地址。' },
                { type: 'list', items: [
                    { label: '分享有效期', desc: '默认分享链接有效期通常为 24 小时。' },
                    { label: '密码保护', desc: '系统会随机生成访问密码，确保只有获得授权的用户才能访问。' },
                    { label: '一键复制', desc: '分享成功后，可一键复制链接和密码发送给对方。' },
                    // 修改：5.png -> files-share-link.png
                    { type: 'image', src: '/images/help/files-share-link.png', caption: '生成的分享链接及提取码界面' },
                ]},

                { type: 'heading', content: '加密卷与存储安全' },
                { type: 'text', content: '系统支持访问受保护的纠删码卷（EC Volume）和加密物理磁盘。' },
                { type: 'list', items: [
                    { label: '加密标识', desc: '侧边栏中带有“纠删码卷”标签的区域受容错保护。' },
                    { label: '锁定状态', desc: '若磁盘已加密，您需要先在磁盘管理中输入密码解锁，才能在文件管理器中看到其内容。' },
                ]},

                { type: 'heading', content: '批量与高级操作' },
                { type: 'list', items: [
                    { label: '多选操作', desc: '按住 Ctrl 键或使用全选按钮，可批量执行下载、移动或删除。' },
                    { label: '搜索过滤', desc: '使用工具栏搜索框，可根据文件名在当前目录下快速过滤。' },
                    { label: '智能路径', desc: '路径栏支持点击跳转，也支持通过“前进/返回”按钮快速导航历史记录。' }
                ]},
                { type: 'warning', content: '在对加密卷或空间池执行删除操作前，请务必确认数据已备份，此类操作无法撤销。' }
            ]
        },

        // ========== 空间池 ==========
        pool: {
            title: '空间池',
            blocks: [
                { type: 'text', content: '空间池可以将多个物理磁盘合并为一个统一的存储空间，并通过"逻辑卷"进行分类管理。' },
                // 修改：6.png -> pool-management.png (且统一放入 /images/help/ 目录)
                { type: 'image', src: '/images/help/pool-management.png', caption: '空间池管理界面' },

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
                { type: 'text', content: '磁盘管理是系统的核心安全与可靠性中心，主要包含“加密管理”与“容错管理（纠删码）”两大功能模块，用于保护数据不被非法访问，并在硬件损坏时确保数据不丢失。' },

                { type: 'heading', content: '🔐 加密管理 (Encryption)' },
                { type: 'text', content: '系统提供工业级的磁盘加密功能，支持物理硬盘和容量池的独立加密。' },
                // 修改：7.png -> disk-encryption-console.png
                { type: 'image', src: '/images/help/disk-encryption-console.png', caption: '磁盘与容量池加密控制台' },
                { type: 'list', items: [
                    { label: '磁盘加密', desc: '为独立物理硬盘设置密码，保护底层数据安全。' },
                    { label: '容量池加密', desc: '支持对整个存储池或池内特定的逻辑卷进行二次加密。' },
                    { label: '锁定/解锁', desc: '加密后的磁盘需手动输入密码解锁后才能在文件管理器中读写。' },
                    { label: '管理操作', desc: '支持在线修改加密密码或永久移除加密（需提供原密码）。' }
                ]},
                { type: 'warning', content: '加密密码不会存储在云端或系统后台，一旦遗忘，数据将无法找回！' },

                { type: 'heading', content: '🛡️ 容错管理 (纠删码/RAID)' },
                { type: 'text', content: '通过纠删码（Erasure Coding）技术，将数据分散存储在多块硬盘上，即使部分硬盘损坏，数据依然完整。' },
                // 修改：8.png -> disk-ec-raid-config.png
                { type: 'image', src: '/images/help/disk-ec-raid-config.png', caption: '容错保护配置与监控' },
                { type: 'list', items: [
                    { label: '配置方案', desc: '支持自定义 K（数据份数）+ M（容错份数）模式。' },
                    { label: '容错能力', desc: '例如 2+1 模式允许同时损坏 1 块硬盘，4+2 模式允许同时损坏 2 块。' },
                    { label: '健康检查', desc: '一键扫描文件块的完整性，识别风险文件和损坏文件。' },
                    { label: '数据修复', desc: '检测到新硬盘替换后，支持批量执行数据重建（Rebuild）。' }
                ]},

                { type: 'heading', content: '硬盘状态监控' },
                { type: 'list', items: [
                    { label: '🟢 在线 (Online)', desc: '硬盘运行正常，数据读写无误。' },
                    { label: '🟡 已更换 (Replaced)', desc: '检测到新硬盘，需要执行数据恢复以重建丢失的切片。' },
                    { label: '🔴 离线 (Offline)', desc: '硬盘连接断开或已损坏，需尽快处理以免超过冗余上限。' }
                ]},
                { type: 'tip', content: '在“容错管理”中，系统会根据磁盘容量差异给出容量预估，建议选择规格接近的硬盘以获得最大空间利用率。' }
            ]
        },

        // ========== 系统信息 ==========
        system: {
            title: '系统信息',
            blocks: [
                { type: 'text', content: '系统信息显示当前NAS节点的运行状态和资源使用情况。' },
                // 修改：9.png -> system-info-dashboard.png
                { type: 'image', src: '/images/help/system-info-dashboard.png', caption: '系统信息界面' },

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
                // 修改：bg-settings.png -> settings-background.png
                { type: 'image', src: '/images/help/settings-background.png', caption: '背景设置' },

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