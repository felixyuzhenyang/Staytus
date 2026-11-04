# PostgreSQL、migration 与容器准备（2026-11-03）

## 当前：Supabase 托管已迁入

- 选用Supabase Free、美国东部的PostgreSQL17；没有购买付费IPv4或升级套餐。使用控制台给出的IPv4 **Session pooler**，不是Transaction模式，连接设置 `sslmode=verify-full` 和项目私有CA bundle。Supabase端强制SSL已开启。
- 当前 `backend/.env` 已指向云端 `staytus_runtime`。主API与工具网关共享这个受限账号；新账号无建库、建角色、绕过RLS、创建持久表或修改migration版本的权限。其他IBM/OAuth/签名/Token加密配置保持不变；失效临时网关地址的恢复另有日志。
- Supabase原始 `postgres` 管理密码仅用于初始化；私有 `.local/supabase/admin.env` 保存管理连接，`migration.env` 使用独立 `staytus_owner`，`runtime.env` 保存运行连接。均0600，不放入Git、产品前端、LLM或Docker镜像。管理员的一次性本机输入页只用于配置交接，成功后已停止，原始交接文件已移除。不同服务端的同名本机／云端角色使用不同凭证。
- Alembic基线 `20261103_0001`、pgvector和25张业务表已建立。先验证云端双账号API/网关共享、伪造所有者拒绝和重启持久化，再停止本机应用写入、备份并将当前PostgreSQL的266条记录／98个总切片逐值导入；原SQLite没有被当作当前数据源。
- 云端Data API关闭；业务表对anon/authenticated/service_role无授权。沿用后端账号和所有权校验，不接Supabase Auth，不向前端提供数据库凭证；GitHub分支自动迁移未启用，Alembic仍是唯一schema版本来源。
- 云端应用级备份为私有、带Alembic版本的SQLite归档，已通过现有 `import-sqlite` 恢复到全新本机PostgreSQL并逐字段核对，再删除临时恢复库。它包含25张应用业务表，不包含Supabase平台自带Auth/Storage配置，不应称为全平台备份或托管PITR。私有proof为 `.local/supabase/cloud-backup-restore-verification.json`。
- 可选embedded本机pg_dump编译时无SSL，无法直接备份云库；官方容器客户端下载也超时，因此本轮使用已验证的TLS驱动生成可移植应用归档。原迁移前本机PostgreSQL完整dump另有保留。后续可配置支持TLS的标准pg_dump和自动备份，不把失败的空dump当作备份。
- 前端、API、网关及定时任务仍在本机；这次完成数据库托管，不等于应用已公开部署。临时工具HTTPS通道、OAuth真人联调、独立调度和公开账号保障仍有各自门槛。
- 迁移后的主Agent Live双账号验证和网页BFF完整聊天调用已通过；测试数据清理完成。聊天开关已恢复，原有政策／提醒／邮箱检查配置均已恢复，三个本机服务健康。现有临时通道曾失效，已在原授权范围内恢复并更新同一Draft/Live连接；没有创建新IBM角色、密钥或重新导入工具。

## 此前本机数据库与容器准备（历史阶段）

- 当前私有开发配置已从 SQLite 切换到真正的 PostgreSQL，不是 mock。主后端与工具网关共用 `DATABASE_URL`。
- 本机无 Docker/PostgreSQL 系统安装，因此在忽略的 `.local/postgres-runtime/` 安装了可移除的 PostgreSQL 运行文件。实际 PostgreSQL18.6，仅监听 `127.0.0.1:55432`；不提供 TLS，也不允许作为公网数据库。云端必须使用托管服务及证书验证。
- 数据目录 `.local/postgres/data/`；未安装开机服务。`backend/.env` 保存有限权限运行连接；`.local/postgres/admin.env` 保存独立迁移连接；均0600。其他 IBM/OAuth 密钥没有修改。
- 迁入25张业务表、266条记录、98个总政策切片（含历史版本；此前87为当前切片），逐字段校验。pgvector使用float32，向量允许明确的微小精度差异。原 SQLite 文件完全不变，另有迁移前 SQLite 备份。
- 旧库有一张空的 `rule_change_proposals` 历史表，保留在 SQLite，不导入当前架构；若它有记录，迁移会拒绝。旧 `retrieval_mode` 声明长度24，目标64，已检查不截断。其他未知结构差异仍拒绝。
- 已完成 PostgreSQL dump → 新临时库恢复 → 全表逐值校验 → 删除该临时库。备份、凭证、运行报告均在 `.local/`，不进Git。
- 独立 API/gateway 进程的双账号隔离、拒绝伪造所有者、网关重启后会话保留均实测通过，合成账号已清理。
- 未创建 IBM 托管 PostgreSQL、Code Engine 应用、域名或新 IBM 凭证。下一轮才配置云端资源和真实 HTTPS。
- 后续已安装Docker Desktop4.98.0，用户本人确认协议后进入Personal免费方案；实际linux/amd64前后端镜像均已本机构建成功，并通过无外网临时容器启动检查。后端启动检查使用合成、临时SQLite，不代表云端PostgreSQL/Orchestrate联调。CI未推送/执行，公网未部署。

## 本机运行

当前电脑已保存Supabase私有连接，日常运行：

```sh
make database-check
make dev
```

地址仍为 http://127.0.0.1:3000。数据库在Supabase，不需要先启动本机PostgreSQL；电脑关机仍会停止本机Web/API/网关和线程调度。下列命令仅启动保留的本机回退数据库，不自动把应用切回去：

```sh
make database-local
make database-check
make dev
```

需要回退时先停止云端应用写入、核对新的云端变化并明确数据切换方案，再修改连接；不能把较旧的本机副本当作自动同步的最新库。不删除本机数据目录。

其他开发者可以使用Docker Compose的PostgreSQL，或者安装可选的本机运行文件：

```sh
uv pip install --python backend/.venv/bin/python --target .local/postgres-runtime 'embedded-postgres==18.6.3'
make database-local
```

`scripts/local_postgres.py start` 只建立本机实例和私有配置，不自动覆盖 `backend/.env`。新项目可把 `.local/postgres/admin.env` 中的URL用于迁移，再为运行配置使用 `runtime.env` 的URL；不要把值放进Git或聊天。

## 版本化结构升级

基线为 `20261103_0001`，包含25张业务表，另有Alembic版本表。当前新增 `20261103_0002`，只为 `user_profiles` 添加默认空对象的 `planning_details` JSON列，已有个人资料不自动填入业务事实。迁移定义在 `backend/app/migrations/versions/`；可审查的生成SQL在 `infra/db/migrations/`。SQL不包含连接信息、个人资料或密钥。历史 SQLite 的显式 adopt 会先核对完整结构，再从匹配的历史版本升级，未知差异仍拒绝。

API/gateway启动只检查版本，不执行 `create_all`、DDL或扩展创建。先以迁移账号运行：

```sh
cd backend
.venv/bin/python -m app.database_cli --env-file ../.local/postgres/admin.env upgrade
.venv/bin/python ../scripts/local_postgres.py grant-runtime
.venv/bin/python -m app.database_cli check
```

`upgrade` 可重复执行，并使用事务级 advisory lock。扩展创建属于迁移工作；云数据库须提前授权或预装pgvector。已有无版本号数据库不会被自动stamp。

`adopt-sqlite` 仅用于结构完全匹配基线、已备份的旧 SQLite；不用于绕过结构差异。实际本轮迁移使用只读SQLite快照和 `import-sqlite`：

```sh
.venv/bin/python -m app.database_cli --env-file ../.local/postgres/admin.env import-sqlite \
  --sqlite-path ../.local/backups/YOUR_SNAPSHOT.db --report ../.local/import-report.json
```

目的库必须空且已迁移；导入时锁定业务表并使用一个事务；失败全部回滚，不合并或覆盖现有记录。先停止API、网关和后台任务。若导入已成功，不要对非空库再次导入。

本轮Supabase迁移从当前PostgreSQL快照读取，没有再次使用旧SQLite。实际使用的目的库迁移配置和源库配置分别保存于私有文件；以下是已完成操作的记录，不能对现有非空库重复导入：

```sh
cd backend
.venv/bin/python -m app.database_cli --env-file ../.local/supabase/migration.env import-postgres \
  --source-env-file ../.local/postgres/admin.env --report ../.local/supabase/import-verification.json
```

该命令要求两端均为当前revision的PostgreSQL，源端使用repeatable-read只读事务，目的端必须为空，锁定全部业务表并逐字段比较后才一次性提交；锁和语句执行有超时，失败回滚全部插入。不修改源库或覆盖目标已有数据。本轮已完成停止写入、备份、TLS、角色与共享访问验证；恢复新库仍须执行同样检查。

新结构变更需要新revision，不修改已经发布的revision。先review生成的DDL，在独立测试库验证，再作为部署中的独立migration步骤运行。downgrade可能删除数据，不应当作生产恢复按钮。

## 两种账号与密钥

- `staytus_owner`：本机迁移/备份账号。真实云端使用服务允许的独立开发/迁移账号，不把它交给API或网关。
- `staytus_runtime`：业务表读写及版本表只读；实测不能建表、不能更新版本表。
- API和网关还必须共用原有 `CONTEXT_SECRET`、`ORCHESTRATE_TOOL_KEY`、`CONNECTOR_TOKEN_KEY`。复制数据库不意味着可以重新随机生成这些密钥；否则既有签名/加密内容可能失效。

迁移Job只需要数据库配置，不需要模型/API/用户授权密钥。若提供 `DATABASE_RUNTIME_ROLE`，`upgrade` 后会显式授予该现有非superuser运行角色权限，并撤销其版本表写入权限。

## 容器

两个Dockerfile都从仓库根目录构建，不能 `COPY ../config` 跨越构建上下文：

```sh
make images
```

- 后端锁定依赖安装，包含migration；运行时读取 `/app/config`，以非root用户执行。同一镜像有 `api`、`gateway`、`migrate`、`check` 角色，支持平台 `PORT`。
- 前端多阶段构建，复制 standalone、静态资源和public目录，以非root用户执行。`BACKEND_URL`、`APP_ORIGIN` 在服务运行时配置；正式运行未配后端地址时返回503，不回退本机地址。
- 根 `.dockerignore` 使用允许列表，排除 `.env`、数据库、备份、`.local`、Bob对话和本机依赖。
- `backend/.env.production.example`、`frontend/.env.production.example` 是平台配置模板；占位符不表示配置完成。生产数据库要求Psycopg3、`sslmode=verify-full`及受信CA；不适用于这个仅loopback、无TLS的本机实例。

Compose先复制 `.env.compose.example` 到忽略的 `.local/compose.env` 并替换独立密码，再执行：

```sh
docker compose --env-file .local/compose.env --profile app up --build
```

Compose会先健康检查数据库、运行migration，再启动API、gateway和前端；默认全部绑定loopback。它不是公网部署。生产前端使用Secure Cookie，完整浏览器/OAuth验证需要配置本机HTTPS代理或云端HTTPS。Compose的三个后台worker明确关闭，须在下一轮配置独立调度；当前 `make dev` 仍按私有后端配置启用已有线程。

## 验证和恢复

```sh
make test
make build
backend/.venv/bin/python scripts/verify_shared_database.py
backend/.venv/bin/python scripts/local_postgres.py backup
backend/.venv/bin/python scripts/local_postgres.py restore-check
```

PostgreSQL套件设置 `STAYTUS_TEST_DATABASE_URL`，只允许数据库名 `staytus_test*`，每个fixture独立schema；不允许应用数据库地址。单元测试仍可使用SQLite，真实外部IBM/OAuth不由这些测试证明。

备份是含私有数据的文件，权限0600。恢复演练创建独立随机临时库，不覆盖运行库。正式恢复须先停止写入、在新库恢复并校验，再切换连接；应用代码、数据库版本和原Token加密密钥要保持兼容。

下一轮云端计算部署：沿用当前Supabase与有限权限账号 → 挂载可信CA并将私有连接存入平台Secrets → 部署API/gateway → 配置稳定HTTPS和Orchestrate连接 → 新的双账号Live验证 → 前端与OAuth回调验证。云端容器不能直接使用本机CA的绝对路径，应更新为挂载路径并重新核对证书。公开注册、OAuth正式验证、账号恢复、共享限流、独立后台调度和运维仍是另外的上线门槛。

## 零付费约束（后续更新）

用户要求尽量不花钱，并于2026-11-03明确选择 **Supabase Free 托管 PostgreSQL**，现已创建并迁入。Docker本地构建使用Personal，无需付费云构建；不创建IBM收费PostgreSQL，也不自动升级任何付费计划。

Supabase Free官网当前列出500MB数据库、最多2个活跃项目，并说明闲置1周后项目会暂停。现有本机库约11MB，仅用于初步判断容量；云端系统占用、索引、增长、连接数和流量仍须实测，不能把免费方案当作持续可用性保证。IBM模型/Orchestrate与未来计算托管费用另行核实。

当前沿用SQLAlchemy/psycopg与Alembic，没有重写为Supabase Auth或前端Data API。Free项目、TLS证书、Session pooler、迁移／受限运行账号、pgvector schema/search_path、迁移事务及跨用户隔离已验证。数据库密码和连接地址只供后端私有配置使用，不进入浏览器或Git。

本轮先用合成数据验证Supabase，再在备份和停止源库写入后导入现有数据；应用级备份恢复也已验证。新的Orchestrate Live结果以 `VERIFICATION.md` 为准。免费容量、暂停规则、后续恢复和计算平台用量应持续监控，不自动升级套餐。

定价核对日期2026-11-03：[Docker](https://www.docker.com/pricing/)、[IBM PostgreSQL](https://cloud.ibm.com/docs/databases-for-postgresql?topic=databases-for-postgresql-pricing)、[Supabase](https://supabase.com/pricing)、[Neon](https://neon.com/pricing)。
