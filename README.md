# 法律日报

给自己部署一个飞书机器人。它在北京时间每天 8:00 发送法律日报和岗位，并另发一份专题材料；每周一另发期刊目录。电脑不用开着。

这是一份模板。每个人使用自己的飞书应用、自己的模型密钥、自己的 GitHub 仓库。关心哪个法律领域，写在 `config.json`，不需要改程序。仓库里的默认配置是一份网络法示例，换领域时把主题、检索词和标题整段换掉。

材料只来自公开网页。页面上没有的法条、论文和岗位不会被写进去。消息末尾会说明这不是法律意见。

## 你会收到什么

- **每日日报**：标题用 `digest_title`。新闻，以及最多若干条岗位。回复「展开第 2 条」或「展开岗位 1」可以展开。
- **专题材料**：标题用 `research_daily_title`。默认示例叫「网络法材料」。每天另发一条。
- **期刊目录**：标题用 `research_weekly_title`。只留 `journal_topics` 里那些方向的题目和链接。每周一另发一条。没有期刊全文。这条不能用「展开」。

## 个性化

编辑仓库根目录的 `config.json`。默认值是网络法示例。换成别的领域时，下面这些字段要一起改，只改读者介绍不够。

| 字段 | 作用 |
| --- | --- |
| `product_name` | 产品名称 |
| `digest_title` | 每日日报的标题 |
| `research_daily_title` | 每天另发的专题材料标题 |
| `research_weekly_title` | 每周一期刊消息的标题 |
| `topic_label` | 短称呼，用在「目录里没有这个主题的题目」 |
| `topics` | 日报和专题材料要留下的主题词 |
| `news_queries` | 新闻检索词。程序会拿它们去搜公开新闻 |
| `news_terms` | 新闻标题或摘要里至少要出现其中一个，才会留下 |
| `job_queries` | 公开网页上的岗位检索词 |
| `job_title_terms` | 公司官网职位标题里至少要出现其中一个 |
| `job_search_terms` | 填进公司官网搜索框的词。不写就用 `job_title_terms` |
| `job_topic_terms` | 公开网页岗位里至少要出现其中一个 |
| `research_queries` | 每天专题材料的检索词 |
| `journal_topics` | 周刊题目里至少要出现其中一个。中文词搜中文期刊，英文词搜英文期刊 |
| `reader.background` | 读者是谁。会写进模型提示 |
| `reader.goal` | 关注什么 |
| `reader.job_order` | 岗位优先级，按数组顺序 |
| `reader.exclude` | 不要的岗位类型 |
| `jobs.fresh_graduate_only` | `true` 时丢掉写明需要 1 年及以上工作经验的职位。「N 年以上经验优先」会保留 |
| `jobs.max_items` | 每天岗位条数 |
| `jobs.companies` | 公司名单。下面 9 家走招聘官网，其他名字用公开网页检索「公司名 招聘」 |
| `news.regions` | 地方新闻优先关注的地区。只影响整理时的提示，不会自动改检索词 |
| `news.max_items` | 每天新闻条数 |
| `journals` | 周刊要看的期刊。可以写书名号，程序会去掉 |

劳动法可以写成这样。期刊名单按你自己要看的来，不要沿用示例里的网络法检索词。

```json
{
  "product_name": "劳动法日报",
  "digest_title": "劳动法日报",
  "research_daily_title": "劳动法材料",
  "research_weekly_title": "劳动法期刊",
  "topic_label": "劳动法",
  "topics": ["劳动合同", "社保", "工伤", "竞业限制"],
  "news_queries": ["劳动合同法 修订 OR 征求意见稿", "最高人民法院 劳动争议 典型案例"],
  "news_terms": ["劳动", "社保", "工伤", "竞业"],
  "job_queries": ["劳动法 律师 招聘", "人力资源 法务 招聘"],
  "job_title_terms": ["劳动", "人力", "法务", "律师"],
  "job_topic_terms": ["劳动", "人力", "法务", "社保"],
  "research_queries": ["劳动合同 司法解释 OR 典型案例", "人力资源社会保障部 规章 OR 通知"],
  "journal_topics": ["劳动", "社保", "用工", "工伤"],
  "journals": ["法学", "中国法学", "中外法学"]
}
```

腾讯、字节跳动、小米、网易、OPPO、百度、美团、滴滴、蚂蚁集团走各自的招聘官网。`jobs.companies` 里的其他名字会用公开网页检索「公司名 招聘」。Boss 直聘、微信公众号、知网和裁判文书网不在这个模板里。

改完 `config.json` 后提交到 `main`，下一次任务就会用新配置。

## 部署前要有的东西

1. 一个飞书企业自建应用。个人如果没有组织，就建不了这个机器人。
2. 一个飞书服务器能在几秒内访问到的 HTTPS 地址。国内云函数可以。`workers.dev` 从飞书访问经常超时，不要用它做回调。
3. DeepSeek 或兼容接口的密钥。接口地址如果不是 DeepSeek，需要改 `legal_daily/llm.py` 里的请求地址。
4. GitHub 仓库，用来放代码和定时任务。

## 1. 使用这份模板

在 GitHub 上点 **Use this template**，新建一个你自己的仓库。也可以克隆后推到你自己的空仓库。

## 2. 放三个 Actions 密钥

仓库 **Settings → Secrets and variables → Actions**：

| 名称 | 填什么 |
| --- | --- |
| `FEISHU_APP_ID` | 飞书 App ID，以 `cli_` 开头 |
| `FEISHU_APP_SECRET` | 飞书 App Secret |
| `DEEPSEEK_API_KEY` | 模型密钥 |

不要新建 `DEEPSEEK_MODEL`，除非你要换模型。不填就用 `deepseek-chat`。

## 3. 准备一把只给云函数用的 GitHub 令牌

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens。

- 只选择这一个仓库
- **Actions** 设为 Read and write
- 如果云函数调用工作流返回 403 或 404，再给 **Contents** 加上 Read

令牌只显示一次。放进云函数的环境变量，不要写进仓库。

推代码如果用 HTTPS，另做一把令牌，**Contents** 和 **Workflows** 都要读写。用户名是 GitHub 用户名，密码是这把令牌。

## 4. 部署接收飞书消息的云函数

以腾讯云函数为例。选事件函数，不要选 Web 函数。运行环境用 Node.js。

- 入口文件 `index.mjs`
- 执行方法 `index.main_handler`
- 把 `worker/scf.js` 的全部内容贴进去。必须是 `export const main_handler`
- 执行超时 10 秒，内存 128MB 或 256MB
- 公网访问打开
- 不要开固定出口 IP、VPC、异步执行

环境变量：

| 名称 | 值 |
| --- | --- |
| `GITHUB_REPO` | `你的用户名/你的仓库` |
| `GITHUB_TOKEN` | 第 3 步那把令牌 |
| `FEISHU_VERIFICATION_TOKEN` | 飞书事件页上的 Verification Token |

部署后复制函数的 HTTPS 地址。

## 5. 把飞书指到这个地址

在飞书开放平台打开你的企业自建应用。

权限至少包括：

- `im:message:send_as_bot`
- `im:message.p2p_msg:readonly`
- `im:message.group_at_msg:readonly`

事件订阅 `im.message.receive_v1`。订阅方式选「把事件发到开发者服务器」。Request URL 填云函数地址。**Encrypt Key 保持空白**。

保存成功后，发布一个新版本。不发布的话，飞书客户端不会生效。

然后给机器人发「你好」。大约一分钟内应收到「已记下这个对话」。之后的日报会发到这个会话。

## 6. 先手动发一次

仓库的 **Actions** 里：

- **每日日报**：右上角 Run workflow，分支选 `main`。当天已经生成过又要重跑时，勾选「同一天再生成一次」。
- **专题材料**：种类选 `daily` 或 `weekly`。这一期已经生成过时，勾选「同一期再生成一次」。默认示例里这两条消息叫网络法材料和网络法期刊，标题以你的 `config.json` 为准。

定时任务是 UTC 0:00，也就是北京时间 8:00，含周末。每周一早上会依次收到日报、专题材料和期刊目录。

## 本地检查

```bash
python3 -m unittest discover -s tests -v
```

## 许可

MIT。见 `LICENSE`。
