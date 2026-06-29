"""
管理数据库 (SQLite) — 表管理/文档管理/权限管理/操作日志

data/admin.db, 服务启动时自动初始化
"""

import json, os, sqlite3, re
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "admin.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """初始化管理数据库，创建表结构，首次运行自动导入达梦表"""
    db = _conn()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS table_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL UNIQUE,
            comment TEXT DEFAULT '',
            budget_type TEXT DEFAULT '其他',
            column_count INTEGER DEFAULT 0,
            is_enabled INTEGER DEFAULT 1,
            columns_json TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS table_regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            region_code TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(table_name, region_code)
        );
        CREATE TABLE IF NOT EXISTS document_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL UNIQUE,
            file_path TEXT DEFAULT '',
            chunk_count INTEGER DEFAULT 0,
            is_enabled INTEGER DEFAULT 1,
            status TEXT DEFAULT 'enabled',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS document_regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            region_code TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(source, region_code)
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_name TEXT NOT NULL,
            detail TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    db.commit()

    # 首次运行自动从达梦导入表列表
    count = db.execute("SELECT COUNT(*) FROM table_metadata").fetchone()[0]
    if count == 0:
        _auto_import_tables(db)

    # 自动从pgvector导入文档列表
    doc_count = db.execute("SELECT COUNT(*) FROM document_metadata").fetchone()[0]
    if doc_count == 0:
        _auto_import_documents(db)

    db.close()
    print(f"[AdminDB] 初始化完成 (data/admin.db)")


def _auto_import_tables(db):
    """从达梦数据库自动导入所有表（含注释）"""
    try:
        from tools import db_connection, db_schema
        if db_connection._connection is None:
            print("[AdminDB] 达梦未连接，跳过自动导入")
            return

        # 获取表注释
        comments = {}
        try:
            cur = db_connection._connection.cursor()
            cur.execute("SELECT TABLE_NAME, COMMENTS FROM ALL_TAB_COMMENTS WHERE OWNER='RDYS_PUBLIC_TBS' AND COMMENTS IS NOT NULL")
            for row in cur.fetchall():
                comments[row[0]] = row[1] if row[1] else ""
        except Exception:
            pass

        tables = []
        for t in db_connection.list_tables().get("tables", []):
            desc = db_schema.describe_table(t)
            comment = comments.get(t, "")
            tables.append((t, comment, desc.get("column_count", 0), json.dumps(desc.get("columns", []), ensure_ascii=False)))

        db.executemany(
            "INSERT INTO table_metadata (table_name, comment, column_count, columns_json) VALUES (?, ?, ?, ?)",
            tables
        )
        for prefix, btype in [("YBGGYS","一般公共预算"),("SHBXJJ","社会保险"),("GYZBJY","国有资本"),("ZFXJJ","政府性基金"),("RDYS_BAS","字典表")]:
            db.execute("UPDATE table_metadata SET budget_type=? WHERE table_name LIKE ?", (btype, f"%{prefix}%"))
        db.commit()
        print(f"[AdminDB] 已导入 {len(tables)} 张表（含注释）")
    except Exception as e:
        print(f"[AdminDB] 自动导入失败: {e}")


def _auto_import_documents(db):
    """从pgvector自动导入文档列表"""
    try:
        from tools.config import config
        db_conn_str = config.RAG_DB_CONNECTION
        coll = config.RAG_COLLECTION
        from sqlalchemy import create_engine, text as sql_text
        engine = create_engine(db_conn_str)
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                f"SELECT c_metadata::jsonb->>'source' as source, COUNT(*) as cnt FROM {coll} GROUP BY source"
            ))
            rows = result.fetchall()
        for row in rows:
            source, cnt = row[0], row[1]
            if source:
                db.execute("INSERT OR IGNORE INTO document_metadata (source, file_path, chunk_count) VALUES (?,?,?)",
                           (source, f"data/{source}", cnt))
        db.commit()
        print(f"[AdminDB] 已导入 {len(rows)} 个文档")
    except Exception as e:
        print(f"[AdminDB] 文档导入失败: {e}")


def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ========== 表管理 ==========

def get_tables(search="", budget_type="", page=1, page_size=20):
    db = _conn()
    where = ["1=1"]
    params = []
    if search:
        where.append("(table_name LIKE ? OR comment LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if budget_type:
        where.append("budget_type = ?")
        params.append(budget_type)

    sql = f"SELECT * FROM table_metadata WHERE {' AND '.join(where)} ORDER BY table_name LIMIT ? OFFSET ?"
    count_sql = f"SELECT COUNT(*) FROM table_metadata WHERE {' AND '.join(where)}"
    rows = [dict(r) for r in db.execute(sql, params + [page_size, (page-1)*page_size]).fetchall()]
    total = db.execute(count_sql, params).fetchone()[0]
    # 追加权限数量
    for r in rows:
        r["region_count"] = db.execute("SELECT COUNT(*) FROM table_regions WHERE table_name=?", (r["table_name"],)).fetchone()[0]
    db.close()
    return {"tables": rows, "total": total, "page": page, "page_size": page_size}


def get_table(table_name):
    db = _conn()
    r = db.execute("SELECT * FROM table_metadata WHERE table_name=?", (table_name,)).fetchone()
    if not r:
        db.close(); return None
    result = dict(r)
    result["columns_json"] = json.loads(result.get("columns_json", "[]"))
    regions = [r["region_code"] for r in db.execute("SELECT region_code FROM table_regions WHERE table_name=?", (table_name,)).fetchall()]
    result["regions"] = regions
    db.close()
    return result


def add_table(table_name, comment="", budget_type=""):
    db = _conn()
    try:
        from tools import db_schema
        desc = db_schema.describe_table(table_name)
        if desc["status"] != "success":
            return {"status": "error", "message": desc.get("message", "表不存在")}
        cols = desc["columns"]
        col_count = len(cols)
        db.execute("INSERT INTO table_metadata (table_name, comment, column_count, columns_json) VALUES (?,?,?,?)",
                   (table_name, comment or "", col_count, json.dumps(cols, ensure_ascii=False)))
        if budget_type:
            db.execute("UPDATE table_metadata SET budget_type=? WHERE table_name=?", (budget_type, table_name))
        db.commit()
        add_log("create", "table", table_name, f"新增表, {col_count}列")
        return {"status": "ok", "table_name": table_name, "column_count": col_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def update_table(table_name, comment=None, budget_type=None):
    db = _conn()
    sets, params = [], []
    if comment is not None: sets.append("comment=?"); params.append(comment)
    if budget_type is not None: sets.append("budget_type=?"); params.append(budget_type)
    if sets:
        sets.append("updated_at=?"); params.append(_now())
        params.append(table_name)
        db.execute(f"UPDATE table_metadata SET {', '.join(sets)} WHERE table_name=?", params)
        db.commit()
        add_log("update", "table", table_name, f"修改: {sets}")
    db.close()
    return {"status": "ok"}


def delete_table(table_name):
    db = _conn()
    db.execute("UPDATE table_metadata SET is_enabled=0, updated_at=? WHERE table_name=?", (_now(), table_name))
    db.commit()
    add_log("disable", "table", table_name, "软删除(禁用)")
    db.close()
    return {"status": "ok"}


def toggle_table(table_name):
    db = _conn()
    r = db.execute("SELECT is_enabled FROM table_metadata WHERE table_name=?", (table_name,)).fetchone()
    if not r: db.close(); return {"status": "error", "message": "表不存在"}
    new_state = 0 if r["is_enabled"] else 1
    db.execute("UPDATE table_metadata SET is_enabled=?, updated_at=? WHERE table_name=?", (new_state, _now(), table_name))
    db.commit()
    add_log("toggle", "table", table_name, f"{'启用' if new_state else '禁用'}")
    db.close()
    return {"status": "ok", "is_enabled": bool(new_state)}


def sync_table(table_name):
    db = _conn()
    try:
        from tools import db_schema
        desc = db_schema.describe_table(table_name)
        if desc["status"] != "success":
            return {"status": "error", "message": desc.get("message","")}
        cols = desc["columns"]
        db.execute("UPDATE table_metadata SET column_count=?, columns_json=?, updated_at=? WHERE table_name=?",
                   (len(cols), json.dumps(cols, ensure_ascii=False), _now(), table_name))
        db.commit()
        add_log("sync", "table", table_name, f"同步列结构, {len(cols)}列")
        return {"status": "ok", "column_count": len(cols)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


# ========== 表地区权限 ==========

def get_table_regions(table_name):
    db = _conn()
    regions = [r["region_code"] for r in db.execute("SELECT region_code FROM table_regions WHERE table_name=?", (table_name,)).fetchall()]
    db.close()
    return {"table_name": table_name, "regions": regions}


def set_table_regions(table_name, regions):
    db = _conn()
    db.execute("DELETE FROM table_regions WHERE table_name=?", (table_name,))
    for rc in regions:
        db.execute("INSERT OR IGNORE INTO table_regions (table_name, region_code) VALUES (?,?)", (table_name, rc))
    db.commit()
    add_log("permission", "table", table_name, f"权限更新: {len(regions)}个地区")
    db.close()
    return {"status": "ok", "region_count": len(regions)}


# ========== 文档管理 ==========

def get_documents(search="", page=1, page_size=12):
    db = _conn()
    where = ["1=1"]
    params = []
    if search:
        where.append("source LIKE ?"); params.append(f"%{search}%")
    sql = f"SELECT * FROM document_metadata WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    rows = [dict(r) for r in db.execute(sql, params + [page_size, (page-1)*page_size]).fetchall()]
    total = db.execute(f"SELECT COUNT(*) FROM document_metadata WHERE {' AND '.join(where)}", params).fetchone()[0]
    for r in rows:
        r["region_count"] = db.execute("SELECT COUNT(*) FROM document_regions WHERE source=?", (r["source"],)).fetchone()[0]
    db.close()
    return {"documents": rows, "total": total, "page": page}


def add_document(source, file_path, chunk_count=0):
    db = _conn()
    db.execute("INSERT OR REPLACE INTO document_metadata (source, file_path, chunk_count, status) VALUES (?,?,?,'enabled')",
               (source, file_path, chunk_count))
    db.commit()
    add_log("create", "document", source, f"新增文档, {chunk_count}片段")
    db.close()
    return {"status": "ok"}


def delete_document(source):
    db = _conn()
    db.execute("UPDATE document_metadata SET is_enabled=0, status='disabled', updated_at=? WHERE source=?", (_now(), source))
    db.commit()
    # 从pgvector移除向量
    try:
        from tools.rag_tool import DB_CONNECTION, COLLECTION_NAME
        from sqlalchemy import create_engine, text as sql_text
        engine = create_engine(DB_CONNECTION)
        with engine.connect() as conn:
            conn.execute(sql_text(f"DELETE FROM {COLLECTION_NAME} WHERE c_metadata::jsonb->>'source' = :src"), {"src": source})
            conn.commit()
    except Exception as e:
        print(f"[AdminDB] 删除向量失败: {e}")
    add_log("delete", "document", source, "删除文档+向量")
    db.close()
    return {"status": "ok"}


def toggle_document(source):
    db = _conn()
    r = db.execute("SELECT is_enabled FROM document_metadata WHERE source=?", (source,)).fetchone()
    if not r: db.close(); return {"status": "error", "message": "文档不存在"}
    new_state = 0 if r["is_enabled"] else 1
    db.execute("UPDATE document_metadata SET is_enabled=?, updated_at=? WHERE source=?", (new_state, _now(), source))
    db.commit()
    add_log("toggle", "document", source, f"{'启用' if new_state else '禁用'}")
    db.close()
    return {"status": "ok", "is_enabled": bool(new_state)}


# ========== 文档权限 ==========

def get_doc_regions(source):
    db = _conn()
    regions = [r["region_code"] for r in db.execute("SELECT region_code FROM document_regions WHERE source=?", (source,)).fetchall()]
    db.close()
    return {"source": source, "regions": regions}


def set_doc_regions(source, regions):
    db = _conn()
    db.execute("DELETE FROM document_regions WHERE source=?", (source,))
    for rc in regions:
        db.execute("INSERT OR IGNORE INTO document_regions (source, region_code) VALUES (?,?)", (source, rc))
    db.commit()
    add_log("permission", "document", source, f"权限更新: {len(regions)}地区")
    db.close()
    return {"status": "ok"}


# ========== 权限总览 ==========

def get_overview(region_code=""):
    db = _conn()
    # 可访问的表
    tables = db.execute("SELECT table_name, comment, budget_type, is_enabled FROM table_metadata WHERE is_enabled=1").fetchall()
    accessible_tables = []
    for t in tables:
        regions = db.execute("SELECT region_code FROM table_regions WHERE table_name=?", (t["table_name"],)).fetchall()
        if not regions or any(_region_match(region_code, r["region_code"]) for r in regions):
            accessible_tables.append(dict(t))
    # 可访问的文档
    docs = db.execute("SELECT source, chunk_count, is_enabled FROM document_metadata WHERE is_enabled=1").fetchall()
    accessible_docs = []
    for d in docs:
        regions = db.execute("SELECT region_code FROM document_regions WHERE source=?", (d["source"],)).fetchall()
        if not regions or any(_region_match(region_code, r["region_code"]) for r in regions):
            accessible_docs.append(dict(d))
    db.close()
    return {"region_code": region_code, "tables": accessible_tables, "documents": accessible_docs,
            "total_tables": len(tables), "total_docs": len(docs)}


def _region_match(user_region, config_region):
    """判断用户地区是否在配置地区的覆盖范围内"""
    if not config_region: return True  # 空权限=不限
    if config_region.endswith("000000"):
        return user_region.startswith(config_region[:2])
    if config_region.endswith("000"):
        return user_region.startswith(config_region[:4])
    return user_region == config_region


# ========== 日志 ==========

def add_log(action, target_type, target_name, detail=""):
    try:
        db = _conn()
        db.execute("INSERT INTO audit_log (action, target_type, target_name, detail) VALUES (?,?,?,?)",
                   (action, target_type, target_name, detail))
        db.commit()
        db.close()
    except Exception:
        pass


def get_logs(page=1, page_size=50):
    db = _conn()
    rows = [dict(r) for r in db.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ? OFFSET ?",
                                         (page_size, (page-1)*page_size)).fetchall()]
    total = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    db.close()
    return {"logs": rows, "total": total, "page": page}


# ========== 权限检查（给 handler.py 用） ==========

def check_table_permission(sql):
    """检查表权限，返回 (can_execute, modified_sql_or_error)"""
    table_name = _extract_table(sql)
    if not table_name:
        return True, sql

    db = _conn()
    meta = db.execute("SELECT is_enabled FROM table_metadata WHERE table_name=?", (table_name,)).fetchone()
    if meta and not meta["is_enabled"]:
        db.close()
        return False, "此表已被管理员禁用"

    regions = [r["region_code"] for r in db.execute("SELECT region_code FROM table_regions WHERE table_name=?", (table_name,)).fetchall()]
    db.close()

    if regions and not _has_rg_condition(sql):
        clause = _build_region_clause(regions)
        sql = _inject_where(sql, clause)

    return True, sql


def _extract_table(sql):
    m = re.search(r'\bFROM\s+([a-zA-Z_][\w.]*)', sql, re.IGNORECASE)
    return m.group(1) if m else ""


def _has_rg_condition(sql):
    return bool(re.search(r'RG_CODE|RG_NAME', sql, re.IGNORECASE))


def _build_region_clause(regions):
    parts = []
    for rc in regions:
        if rc.endswith("000000"): parts.append(f"RG_CODE LIKE '{rc[:2]}%'")
        elif rc.endswith("000"): parts.append(f"RG_CODE LIKE '{rc[:4]}%'")
        else: parts.append(f"RG_CODE = '{rc}'")
    return "(" + " OR ".join(parts) + ")" if len(parts) > 1 else parts[0]


def _inject_where(sql, clause):
    """在WHERE子句中注入地区过滤条件"""
    if re.search(r'\bWHERE\b', sql, re.IGNORECASE):
        return re.sub(r'\bWHERE\b', f'WHERE {clause} AND ', sql, count=1, flags=re.IGNORECASE)
    elif re.search(r'\bGROUP BY\b', sql, re.IGNORECASE):
        return re.sub(r'\bGROUP BY\b', f'WHERE {clause} GROUP BY', sql, count=1, flags=re.IGNORECASE)
    elif re.search(r'\bORDER BY\b', sql, re.IGNORECASE):
        return re.sub(r'\bORDER BY\b', f'WHERE {clause} ORDER BY', sql, count=1, flags=re.IGNORECASE)
    else:
        return sql + f" WHERE {clause}"
