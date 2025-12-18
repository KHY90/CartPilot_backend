"""
LangGraph 그래프 시각화 유틸리티
"""
import os
from pathlib import Path
from typing import Optional


def get_graph_mermaid() -> str:
    """
    오케스트레이터 그래프를 Mermaid 다이어그램으로 반환

    Returns:
        Mermaid 다이어그램 문자열
    """
    from app.agents.orchestrator import build_orchestrator

    orchestrator = build_orchestrator()
    return orchestrator.get_graph().draw_mermaid()


def get_graph_ascii() -> str:
    """
    오케스트레이터 그래프를 ASCII로 반환

    Returns:
        ASCII 다이어그램 문자열
    """
    from app.agents.orchestrator import build_orchestrator

    orchestrator = build_orchestrator()
    return orchestrator.get_graph().draw_ascii()


def save_graph_png(output_path: Optional[str] = None) -> str:
    """
    오케스트레이터 그래프를 PNG 이미지로 저장

    Args:
        output_path: 저장 경로 (기본값: Backend/docs/graph.png)

    Returns:
        저장된 파일 경로
    """
    from app.agents.orchestrator import build_orchestrator

    if output_path is None:
        # Backend/docs 디렉토리에 저장
        backend_dir = Path(__file__).parent.parent.parent
        docs_dir = backend_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        output_path = str(docs_dir / "graph.png")

    orchestrator = build_orchestrator()

    try:
        # PNG 생성 (pygraphviz 필요)
        png_data = orchestrator.get_graph().draw_mermaid_png()

        with open(output_path, "wb") as f:
            f.write(png_data)

        return output_path
    except Exception as e:
        raise RuntimeError(
            f"PNG 생성 실패. 인터넷 연결을 확인하세요: {e}"
        )


def save_graph_mermaid(output_path: Optional[str] = None) -> str:
    """
    오케스트레이터 그래프를 Mermaid 파일로 저장

    Args:
        output_path: 저장 경로 (기본값: Backend/docs/graph.md)

    Returns:
        저장된 파일 경로
    """
    if output_path is None:
        backend_dir = Path(__file__).parent.parent.parent
        docs_dir = backend_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        output_path = str(docs_dir / "graph.md")

    mermaid_code = get_graph_mermaid()

    content = f"""# CartPilot LangGraph 흐름도

```mermaid
{mermaid_code}
```

## 노드 설명

| 노드 | 설명 |
|------|------|
| `__start__` | 시작점 |
| `analyze_request` | 사용자 요청 분석 (의도 분류 + 요구사항 추출) |
| `clarify` | 추가 정보 요청 필요시 |
| `route_by_intent` | 의도별 에이전트 라우팅 |
| `gift_agent` | 선물 추천 (GIFT 모드) |
| `value_agent` | 가성비 추천 (VALUE 모드) |
| `bundle_agent` | 묶음 구매 (BUNDLE 모드) |
| `review_agent` | 리뷰 분석 (REVIEW 모드) |
| `trend_agent` | 트렌드 추천 (TREND 모드) |
| `__end__` | 종료점 |
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path


if __name__ == "__main__":
    import sys

    print("=" * 50)
    print("CartPilot LangGraph 시각화")
    print("=" * 50)

    # Mermaid 다이어그램 출력
    print("\n[Mermaid 다이어그램]")
    print("-" * 50)
    print(get_graph_mermaid())

    # ASCII 다이어그램 출력
    print("\n[ASCII 다이어그램]")
    print("-" * 50)
    print(get_graph_ascii())

    # 파일 저장
    print("\n[파일 저장]")
    print("-" * 50)

    # Mermaid 파일 저장
    mermaid_path = save_graph_mermaid()
    print(f"Mermaid 저장됨: {mermaid_path}")

    # PNG 저장 시도
    try:
        png_path = save_graph_png()
        print(f"PNG 저장됨: {png_path}")
    except Exception as e:
        print(f"PNG 저장 실패 (graphviz 필요): {e}")

    print("\n완료!")
