#!/usr/bin/env python3
"""
LangGraph 시각화 스크립트

사용법:
    python scripts/visualize_graph.py [옵션]

옵션:
    --format, -f    출력 형식 (mermaid, ascii, png, all) [기본값: all]
    --output, -o    출력 디렉토리 [기본값: docs/]
    --print, -p     콘솔에 출력

예시:
    python scripts/visualize_graph.py
    python scripts/visualize_graph.py -f png
    python scripts/visualize_graph.py -f mermaid -p
    python scripts/visualize_graph.py -o ./output
"""
import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(
        description="CartPilot LangGraph 시각화",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
    python scripts/visualize_graph.py              # 모든 형식으로 docs/에 저장
    python scripts/visualize_graph.py -f png       # PNG만 저장
    python scripts/visualize_graph.py -f ascii -p  # ASCII를 콘솔에 출력
    python scripts/visualize_graph.py -o ./output  # output/ 디렉토리에 저장
        """,
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["mermaid", "ascii", "png", "all"],
        default="all",
        help="출력 형식 (기본값: all)",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="출력 디렉토리 (기본값: docs/)",
    )

    parser.add_argument(
        "-p",
        "--print",
        action="store_true",
        help="콘솔에 출력",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  CartPilot LangGraph Visualizer")
    print("=" * 60)
    print()

    from app.utils.graph_visualizer import (
        get_graph_ascii,
        get_graph_mermaid,
        save_graph_mermaid,
        save_graph_png,
    )

    output_dir = args.output
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    # Mermaid
    if args.format in ["mermaid", "all"]:
        print("[Mermaid 다이어그램]")
        print("-" * 40)

        if args.print:
            print(get_graph_mermaid())
            print()

        mermaid_path = None
        if output_dir:
            mermaid_path = str(output_dir / "graph.md")

        saved_path = save_graph_mermaid(mermaid_path)
        print(f"저장됨: {saved_path}")
        print()

    # ASCII
    if args.format in ["ascii", "all"]:
        print("[ASCII 다이어그램]")
        print("-" * 40)

        if args.print or args.format == "ascii":
            print(get_graph_ascii())
            print()

    # PNG
    if args.format in ["png", "all"]:
        print("[PNG 이미지]")
        print("-" * 40)

        try:
            png_path = None
            if output_dir:
                png_path = str(output_dir / "graph.png")

            saved_path = save_graph_png(png_path)
            print(f"저장됨: {saved_path}")
        except Exception as e:
            print(f"PNG 생성 실패: {e}")
            print("힌트: 인터넷 연결을 확인하세요 (Mermaid API 사용)")

        print()

    print("=" * 60)
    print("  완료!")
    print("=" * 60)

    # 웹 뷰어 안내
    print()
    print("웹 브라우저에서 보기:")
    print("  1. 서버 실행: uvicorn app.main:app --reload")
    print("  2. 브라우저에서 http://localhost:8000/api/graph 접속")


if __name__ == "__main__":
    main()
