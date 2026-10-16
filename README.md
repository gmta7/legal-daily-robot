# 法律日报

给自己部署一个飞书机器人。它在北京时间每天 8:00 发送法律与合规日报、岗位，并另发网络法材料；每周一另发期刊目录。电脑不用开着。

这是一份模板。每个人使用自己的飞书应用、自己的模型密钥、自己的 GitHub 仓库。读者身份、期刊、公司和关注地区写在 `config.json`，不需要改程序。

材料只来自公开网页。页面上没有的法条、论文和岗位不会被写进去。消息末尾会说明这不是法律意见。

## 你会收到什么

- **每日日报**：新闻，以及最多若干条岗位。回复「展开第 2 条」或「展开岗位 1」可以展开。
- **网络法材料**：新规、北京/杭州/广州互联网法院、时评和公开活动。每天另发一条。
- **网络法期刊**：`config.json` 里期刊的公开目录，只留网络法、数据、人工智能相关的题目和链接。每周一另发一条。没有期刊全文。这条不能用「展开」。

## 个性化

编辑仓库根目录的 `config.json`。

| 字段 | 作用 |
| --- | --- |
| `reader.background` | 读者是谁。会写进模型提示 |
| `reader.goal` | 关注什么 |
| `reader.job_order` | 岗位优先级，按数组顺序 |
| `reader.exclude` | 不要的岗位类型 |
| `jobs.fresh_graduate_only` | `true` 时丢掉写明需要 1 年及以上工作经验的职位。「N 年以上经验优先」会保留 |
| `jobs.max_items` | 每天岗位条数 |
| `jobs.companies` | 要抓的公司官网。只能填下面已经接通的名字 |
| `news.regions` | 地方新闻优先关注的地区 |
| `news.max_items` | 每天新闻条数 |
| `journals` | 周刊要看的期刊。可以写书名号，程序会去掉 |

已经接通的公司官网：腾讯、字节跳动、小米、网易、OPPO、百度、美团、滴滴、蚂蚁集团。名单里写了别的名字也不会去抓。Boss 直聘、微信公众号、知网和裁判文书网不在这个模板里。

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
- **网络法材料**：种类选 `daily` 或 `weekly`。这一期已经生成过时，勾选「同一期再生成一次」。

定时任务是 UTC 0:00，也就是北京时间 8:00，含周末。每周一早上会依次收到日报、网络法材料、网络法期刊。

## 本地检查

```bash
python3 -m unittest discover -s tests -v
```

## 许可

MIT。见 `LICENSE`。
