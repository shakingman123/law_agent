backend
    .venv #配置
    app 
        agents
            archive
                densensitize.py #对文件的信息进行脱敏，采用的是正则结构化和NER补充
                graph.py #把脱敏放入graph,并把脱敏后数据放入LegalReference 两个todo 病毒扫描和加密上传 已完成

            drafting
                tools.py #按照模板id取模板，把信息填入占位符，生成word\pdf文书 模板需要处理，才会显示占位符
                graph.py #临时储存MemorySaver，文书生成处理 
            legal_search
                graph.py # 搜索法条，还未接入Qdrant 已完成
            reminder
                graph.py #生成截至时间并在时间到达前提醒 自定义多少天前提醒，在文书中的最后获取时间，在相依的案件库中生成时间轴
        api
            cases # 最近 1 周打开的案件，相同的案件只出现一次   已解决
            conversations.py #登录状态时，记忆历史会话记录。退出登录或者关闭网页，刷新对话。
            templates #示例模板太简略了，需要更换
        core
            config #数据库连接串（开发环境 SQLite）生产环境需要更改配置
        llm
            gateway #配置模型api，关于平台开发者key，在生产环境是否需要
            