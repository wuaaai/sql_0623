"""
Text-to-SQL 命令行入口

用法:
    python main.py                          # 交互模式
    python main.py "查询users表的所有数据"   # 单次查询

配置 (环境变量):
    OPENAI_API_KEY   - API密钥 (必须)
    OPENAI_BASE_URL  - API地址 (默认 https://api.openai.com/v1)
    OPENAI_MODEL     - 模型名 (默认 gpt-4o)
"""

import os
import sys
from agent_core import TextToSQLAgent


def main():
    # 检查 API Key
    if not os.environ.get("OPENAI_API_KEY"):
        print("错误: 请设置环境变量 OPENAI_API_KEY")
        print("例如: export OPENAI_API_KEY=sk-xxx")
        sys.exit(1)

    print("=" * 50)
    print("  Text-to-SQL Agent")
    print(f"  Model: {os.environ.get('OPENAI_MODEL', 'gpt-4o')}")
    print(f"  Base URL: {os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')}")
    print("=" * 50)
    print()
    print("使用说明:")
    print("  1. 先用 connect_db 连接数据库")
    print("  2. 用自然语言描述查询需求")
    print("  3. 输入 /quit 退出")
    print()

    agent = TextToSQLAgent()

    # 单次查询模式
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f">>> {query}\n")
        for chunk in agent.run(query):
            print(chunk, end="", flush=True)
        print()
        return

    # 交互模式
    while True:
        try:
            user_input = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("再见！")
            break

        for chunk in agent.run(user_input):
            print(chunk, end="", flush=True)
        print()


if __name__ == "__main__":
    main()
