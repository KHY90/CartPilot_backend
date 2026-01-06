"""
가격 예측 서비스
90일 가격 이력 기반 추세 분석 + Prophet 시계열 예측 + 세일 시즌 캘린더 활용
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
from prophet import Prophet

from app.models.price_prediction import (
    PriceHistoryPoint,
    PricePrediction,
    PriceTrend,
    PredictionSummary,
    UpcomingSale,
)

# Prophet 로깅 비활성화 (너무 많은 로그 방지)
logging.getLogger('prophet').setLevel(logging.WARNING)
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)


class PricePredictor:
    """가격 예측 서비스"""

    # 최소 데이터 포인트 수 (이 이하면 데이터 부족으로 판단)
    MIN_DATA_POINTS = 7

    def __init__(self):
        self._sale_calendar: dict | None = None
        self._calendar_path = Path(__file__).parent.parent / "data" / "sale_calendar.json"

    @property
    def sale_calendar(self) -> dict:
        """세일 캘린더 데이터 (lazy loading)"""
        if self._sale_calendar is None:
            try:
                with open(self._calendar_path, "r", encoding="utf-8") as f:
                    self._sale_calendar = json.load(f)
            except FileNotFoundError:
                self._sale_calendar = {
                    "lunar_holidays": {},
                    "annual_sales": [],
                    "special_days": [],
                    "category_seasonality": {},
                }
        return self._sale_calendar

    def _get_lunar_holiday_dates(
        self,
        holiday_name: str,
        year: int,
    ) -> Optional[Tuple[datetime, datetime]]:
        """
        음력 명절의 실제 양력 날짜 조회

        Args:
            holiday_name: 명절 이름 (설날, 추석)
            year: 연도

        Returns:
            (시작일, 종료일) 튜플 또는 None
        """
        lunar_holidays = self.sale_calendar.get("lunar_holidays", {})
        holiday_data = lunar_holidays.get(holiday_name, {})
        year_data = holiday_data.get(str(year))

        if not year_data:
            return None

        try:
            start_date = datetime.strptime(f"{year}-{year_data['start']}", "%Y-%m-%d")
            end_date = datetime.strptime(f"{year}-{year_data['end']}", "%Y-%m-%d")
            return (start_date, end_date)
        except (ValueError, KeyError):
            return None

    def _check_category_match(
        self,
        product_category: Optional[str],
        sale_categories: List[str],
    ) -> bool:
        """
        상품 카테고리와 세일 카테고리 매칭 확인

        Args:
            product_category: 상품 카테고리
            sale_categories: 세일 적용 카테고리 목록

        Returns:
            bool: 적용 가능 여부
        """
        if "전체" in sale_categories:
            return True

        if not product_category:
            # 카테고리 없으면 일단 적용 가능으로 표시
            return True

        category_lower = product_category.lower()
        for sc in sale_categories:
            sc_lower = sc.lower()
            if sc_lower in category_lower or category_lower in sc_lower:
                return True

        return False

    def analyze_trend(
        self,
        price_history: List[Tuple[datetime, int]],
        period_days: int = 30,
    ) -> PriceTrend:
        """
        가격 추세 분석

        Args:
            price_history: [(날짜, 가격)] 리스트 (최신순 정렬)
            period_days: 분석 기간 (일)

        Returns:
            PriceTrend: 추세 방향, 변동률, 분석 기간
        """
        if len(price_history) < 2:
            return PriceTrend(
                direction="stable",
                change_rate=0.0,
                period_days=period_days,
            )

        # 기간 내 데이터 필터링
        cutoff = datetime.utcnow() - timedelta(days=period_days)
        filtered = [(dt, price) for dt, price in price_history if dt >= cutoff]

        if len(filtered) < 2:
            # 기간 내 데이터 부족 시 전체 데이터 사용
            filtered = price_history[:min(10, len(price_history))]

        if len(filtered) < 2:
            return PriceTrend(
                direction="stable",
                change_rate=0.0,
                period_days=period_days,
            )

        # 시간순 정렬 (오래된 것부터)
        filtered.sort(key=lambda x: x[0])

        # 시작가와 끝가 비교
        start_price = filtered[0][1]
        end_price = filtered[-1][1]

        if start_price == 0:
            return PriceTrend(
                direction="stable",
                change_rate=0.0,
                period_days=period_days,
            )

        change_rate = ((end_price - start_price) / start_price) * 100

        # 방향 결정 (5% 임계값)
        if change_rate > 5:
            direction = "up"
        elif change_rate < -5:
            direction = "down"
        else:
            direction = "stable"

        return PriceTrend(
            direction=direction,
            change_rate=round(change_rate, 1),
            period_days=period_days,
        )

    def _predict_with_prophet(
        self,
        price_history: List[Tuple[datetime, int]],
    ) -> Tuple[Optional[int], Optional[int], float]:
        """
        Prophet으로 7일/30일 후 가격 예측

        Args:
            price_history: [(날짜, 가격)] 리스트

        Returns:
            (7일 후 예측가, 30일 후 예측가, 신뢰도)
        """
        try:
            # DataFrame 생성 (Prophet 형식: ds, y)
            df = pd.DataFrame(price_history, columns=['ds', 'y'])
            df['ds'] = pd.to_datetime(df['ds'])
            df = df.sort_values('ds').drop_duplicates(subset=['ds'])

            if len(df) < 14:
                # 데이터 너무 적으면 Prophet 사용 불가
                return None, None, 0.3

            # Prophet 모델 생성 (간단한 설정)
            model = Prophet(
                yearly_seasonality=False,  # 1년 데이터 없으므로 비활성화
                weekly_seasonality=True,   # 주간 패턴 감지
                daily_seasonality=False,   # 일간 패턴 불필요
                changepoint_prior_scale=0.05,  # 추세 변화 민감도 (낮을수록 부드러움)
            )

            # 모델 학습
            model.fit(df)

            # 미래 30일 예측
            future = model.make_future_dataframe(periods=30)
            forecast = model.predict(future)

            # 7일, 30일 후 예측값 추출
            current_date = df['ds'].max()
            pred_7d_date = current_date + timedelta(days=7)
            pred_30d_date = current_date + timedelta(days=30)

            forecast_7d = forecast[forecast['ds'] >= pred_7d_date].head(1)
            forecast_30d = forecast[forecast['ds'] >= pred_30d_date].head(1)

            predicted_7d = None
            predicted_30d = None

            if not forecast_7d.empty:
                predicted_7d = max(0, int(forecast_7d['yhat'].values[0]))

            if not forecast_30d.empty:
                predicted_30d = max(0, int(forecast_30d['yhat'].values[0]))

            # 신뢰도 계산 (데이터 양과 예측 불확실성 기반)
            confidence = self._calculate_prophet_confidence(df, forecast)

            return predicted_7d, predicted_30d, confidence

        except Exception as e:
            # Prophet 오류 시 fallback
            logging.warning(f"Prophet prediction failed: {e}")
            return None, None, 0.3

    def _calculate_prophet_confidence(
        self,
        df: pd.DataFrame,
        forecast: pd.DataFrame,
    ) -> float:
        """Prophet 예측 신뢰도 계산"""
        confidence = 0.5

        # 데이터 포인트 수에 따른 보정
        data_points = len(df)
        if data_points >= 60:
            confidence += 0.25
        elif data_points >= 30:
            confidence += 0.15
        elif data_points >= 14:
            confidence += 0.05

        # 예측 불확실성 (yhat_upper - yhat_lower) 기반 보정
        if not forecast.empty and 'yhat_upper' in forecast.columns:
            last_forecast = forecast.tail(1)
            uncertainty = (
                last_forecast['yhat_upper'].values[0] -
                last_forecast['yhat_lower'].values[0]
            )
            current_price = df['y'].iloc[-1]

            if current_price > 0:
                uncertainty_ratio = uncertainty / current_price
                if uncertainty_ratio < 0.1:
                    confidence += 0.1
                elif uncertainty_ratio > 0.3:
                    confidence -= 0.1

        return max(0.2, min(0.9, round(confidence, 2)))

    def get_upcoming_sales(
        self,
        category: Optional[str] = None,
        days_ahead: int = 60,
    ) -> List[UpcomingSale]:
        """
        다가오는 세일 조회

        Args:
            category: 상품 카테고리 (선택)
            days_ahead: 몇 일 앞까지 조회할지

        Returns:
            List[UpcomingSale]: 다가오는 세일 목록
        """
        now = datetime.utcnow()
        current_year = now.year
        upcoming: List[UpcomingSale] = []

        for sale in self.sale_calendar.get("annual_sales", []):
            sale_type = sale.get("type", "fixed")

            # 올해와 내년 모두 확인
            for year in [current_year, current_year + 1]:
                start_date = None
                end_date = None

                if sale_type == "lunar":
                    # 음력 명절 기반 세일
                    lunar_holiday = sale.get("lunar_holiday")
                    if not lunar_holiday:
                        continue

                    holiday_dates = self._get_lunar_holiday_dates(lunar_holiday, year)
                    if not holiday_dates:
                        continue

                    holiday_start, holiday_end = holiday_dates
                    days_before = sale.get("days_before", 14)
                    days_after = sale.get("days_after", 0)

                    start_date = holiday_start - timedelta(days=days_before)
                    end_date = holiday_end + timedelta(days=days_after)
                else:
                    # 고정 날짜 세일
                    start_month = sale.get("start_month")
                    start_day = sale.get("start_day")
                    end_month = sale.get("end_month")
                    end_day = sale.get("end_day")

                    if not all([start_month, start_day, end_month, end_day]):
                        continue

                    try:
                        start_date = datetime(year, start_month, start_day)
                        end_date = datetime(year, end_month, end_day)

                        # 연도를 넘어가는 세일 처리 (예: 12월 26일 ~ 1월 5일)
                        if end_month < start_month:
                            end_date = datetime(year + 1, end_month, end_day)
                    except ValueError:
                        continue

                if not start_date or not end_date:
                    continue

                # 이미 종료된 세일 건너뛰기
                if end_date < now:
                    continue

                # 너무 먼 미래 세일 건너뛰기
                days_until = (start_date - now).days
                if days_until > days_ahead:
                    continue

                # 이미 진행 중인 세일
                if start_date <= now <= end_date:
                    days_until = 0

                # 카테고리 적용 가능 여부 확인
                sale_categories = sale.get("categories", [])
                applicable = self._check_category_match(category, sale_categories)

                upcoming.append(
                    UpcomingSale(
                        name=sale["name"],
                        start_date=start_date.strftime("%Y-%m-%d"),
                        end_date=end_date.strftime("%Y-%m-%d"),
                        days_until=max(0, days_until),
                        expected_discount=sale.get("discount_rate", 0),
                        applicable=applicable,
                    )
                )
                break  # 같은 세일은 한 번만 추가

        # 특별 할인일 처리
        for special in self.sale_calendar.get("special_days", []):
            month = special["month"]
            day_range = special.get("day_range", [1, 28])

            for year in [current_year, current_year + 1]:
                try:
                    start_date = datetime(year, month, day_range[0])
                    end_date = datetime(year, month, day_range[1])
                except ValueError:
                    continue

                if end_date < now:
                    continue

                days_until = (start_date - now).days
                if days_until > days_ahead:
                    continue

                if start_date <= now <= end_date:
                    days_until = 0

                # 카테고리 적용 여부
                special_categories = special.get("categories", [])
                applicable = self._check_category_match(category, special_categories)

                upcoming.append(
                    UpcomingSale(
                        name=special["name"],
                        start_date=start_date.strftime("%Y-%m-%d"),
                        end_date=end_date.strftime("%Y-%m-%d"),
                        days_until=max(0, days_until),
                        expected_discount=special.get("discount_rate", 0),
                        applicable=applicable,
                    )
                )
                break

        # D-day 순으로 정렬
        upcoming.sort(key=lambda x: x.days_until)

        return upcoming

    def predict(
        self,
        product_id: str,
        current_price: int,
        price_history: List[Tuple[datetime, int]],
        category: Optional[str] = None,
    ) -> PricePrediction:
        """
        가격 예측 수행

        Args:
            product_id: 상품 ID
            current_price: 현재 가격
            price_history: [(날짜, 가격)] 리스트
            category: 상품 카테고리

        Returns:
            PricePrediction: 가격 예측 결과
        """
        # 1. 추세 분석
        trend = self.analyze_trend(price_history, period_days=30)

        # 2. 90일 최저/최고가 계산
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)
        recent_history = [(dt, price) for dt, price in price_history if dt >= ninety_days_ago]

        lowest_90d = None
        highest_90d = None

        if recent_history:
            prices = [price for _, price in recent_history]
            lowest_90d = min(prices)
            highest_90d = max(prices)

        # 3. 예측 가격 계산
        predicted_7d = None
        predicted_30d = None
        prophet_confidence = None

        # 14일 이상 데이터가 있으면 Prophet 사용
        if len(price_history) >= 14:
            prophet_7d, prophet_30d, prophet_conf = self._predict_with_prophet(price_history)
            if prophet_7d is not None or prophet_30d is not None:
                predicted_7d = prophet_7d
                predicted_30d = prophet_30d
                prophet_confidence = prophet_conf

        # Prophet 실패 또는 데이터 부족 시 단순 추세 외삽 (fallback)
        if predicted_7d is None and len(price_history) >= 7 and trend.change_rate != 0:
            daily_change_rate = trend.change_rate / trend.period_days
            predicted_7d = int(current_price * (1 + (daily_change_rate * 7) / 100))
            predicted_30d = int(current_price * (1 + (daily_change_rate * 30) / 100))

        # 4. 다가오는 세일 조회
        upcoming_sales = self.get_upcoming_sales(category=category, days_ahead=60)

        # 5. 신뢰도 계산
        if prophet_confidence is not None:
            confidence = prophet_confidence
        else:
            confidence = self._calculate_confidence(price_history, trend)

        # 6. 구매 추천 결정
        buy_recommendation, recommendation_reason, best_buy_timing = self._make_recommendation(
            current_price=current_price,
            lowest_90d=lowest_90d,
            trend=trend,
            upcoming_sales=upcoming_sales,
            data_points=len(price_history),
        )

        return PricePrediction(
            product_id=product_id,
            current_price=current_price,
            trend=trend,
            lowest_price_90d=lowest_90d,
            highest_price_90d=highest_90d,
            predicted_price_7d=predicted_7d,
            predicted_price_30d=predicted_30d,
            confidence=confidence,
            upcoming_sales=upcoming_sales[:3],  # 상위 3개만
            best_buy_timing=best_buy_timing,
            buy_recommendation=buy_recommendation,
            recommendation_reason=recommendation_reason,
            history_points=len(price_history),
        )

    def _calculate_confidence(
        self,
        price_history: List[Tuple[datetime, int]],
        trend: PriceTrend,
    ) -> float:
        """예측 신뢰도 계산"""
        # 기본 신뢰도 0.5
        confidence = 0.5

        # 데이터 포인트 수에 따른 보정
        if len(price_history) >= 30:
            confidence += 0.2
        elif len(price_history) >= 14:
            confidence += 0.1
        elif len(price_history) < 7:
            confidence -= 0.2

        # 안정적 추세일수록 신뢰도 상승
        if trend.direction == "stable":
            confidence += 0.1

        # 변동률이 너무 크면 신뢰도 하락
        if abs(trend.change_rate) > 20:
            confidence -= 0.15
        elif abs(trend.change_rate) > 10:
            confidence -= 0.05

        return max(0.1, min(0.95, round(confidence, 2)))

    def _make_recommendation(
        self,
        current_price: int,
        lowest_90d: Optional[int],
        trend: PriceTrend,
        upcoming_sales: List[UpcomingSale],
        data_points: int = 0,
    ) -> Tuple[str, str, str]:
        """
        구매 추천 결정

        Args:
            current_price: 현재 가격
            lowest_90d: 90일 최저가
            trend: 가격 추세
            upcoming_sales: 다가오는 세일 목록
            data_points: 가격 데이터 포인트 수

        Returns:
            (recommendation, reason, best_timing)
        """
        # 데이터 부족 시 세일 정보 기반 추천만 제공
        if data_points < self.MIN_DATA_POINTS:
            # 적용 가능한 세일이 곧 있는 경우
            applicable_sales = [s for s in upcoming_sales if s.applicable and s.days_until <= 30]

            if applicable_sales:
                nearest_sale = applicable_sales[0]

                if nearest_sale.days_until == 0:
                    return (
                        "neutral",
                        f"[예상 세일] {nearest_sale.name} 기간입니다. 실제 할인 여부는 쇼핑몰에서 직접 확인해주세요.",
                        f"{nearest_sale.name} 예상 기간",
                    )

                if nearest_sale.days_until <= 14 and nearest_sale.expected_discount >= 15:
                    return (
                        "neutral",
                        f"[예상 세일] {nearest_sale.days_until}일 후 {nearest_sale.name} 예상 기간입니다. 실제 할인은 쇼핑몰에서 확인하세요.",
                        f"{nearest_sale.days_until}일 후 예상 세일",
                    )

            # 데이터 부족으로 정확한 분석 불가
            return (
                "neutral",
                f"가격 데이터가 부족합니다 ({data_points}일 / {self.MIN_DATA_POINTS}일 필요). 며칠 후 다시 확인해주세요.",
                "가격 데이터 수집 중",
            )

        # 현재가 = 90일 최저가 (데이터가 충분할 때만)
        if lowest_90d and current_price <= lowest_90d:
            return (
                "buy_now",
                "현재 가격이 90일 최저가입니다. 지금 구매하시는 것이 좋습니다.",
                "지금이 최적 구매 시점입니다",
            )

        # 적용 가능한 예상 세일이 곧 있는 경우 (가격 추세와 함께 고려)
        applicable_sales = [s for s in upcoming_sales if s.applicable and s.days_until <= 30]

        # 가격 하락 추세
        if trend.direction == "down" and trend.change_rate < -5:
            return (
                "wait",
                f"최근 30일간 {abs(trend.change_rate):.1f}% 하락 추세입니다. 조금 더 기다리면 더 저렴하게 구매할 수 있습니다.",
                "가격 하락 추세, 1-2주 대기 추천",
            )

        # 가격 상승 추세
        if trend.direction == "up" and trend.change_rate > 5:
            return (
                "buy_now",
                f"최근 30일간 {trend.change_rate:.1f}% 상승 추세입니다. 더 오르기 전에 구매하는 것이 좋습니다.",
                "가격 상승 추세, 빠른 구매 추천",
            )

        # 중립
        if applicable_sales:
            nearest_sale = applicable_sales[0]
            return (
                "neutral",
                f"현재 가격이 적정 수준입니다. {nearest_sale.days_until}일 후 {nearest_sale.name} 예상 기간이 있으니 참고하세요. (실제 할인은 쇼핑몰에서 확인)",
                "적정 가격, 예상 세일 참고",
            )

        return (
            "neutral",
            "현재 가격이 적정 수준입니다. 가격 변동을 지켜보세요.",
            "적정 가격",
        )

    def get_summary(
        self,
        predictions: List[PricePrediction],
    ) -> PredictionSummary:
        """
        여러 상품의 예측 결과 요약

        Args:
            predictions: 예측 결과 리스트

        Returns:
            PredictionSummary: 요약 정보
        """
        buy_now_count = sum(1 for p in predictions if p.buy_recommendation == "buy_now")
        wait_count = sum(1 for p in predictions if p.buy_recommendation == "wait")
        neutral_count = sum(1 for p in predictions if p.buy_recommendation == "neutral")

        # 가장 가까운 세일 찾기
        all_sales: List[UpcomingSale] = []
        for p in predictions:
            all_sales.extend(p.upcoming_sales)

        next_sale = None
        if all_sales:
            # 적용 가능한 세일 중 가장 가까운 것
            applicable_sales = [s for s in all_sales if s.applicable]
            if applicable_sales:
                applicable_sales.sort(key=lambda x: x.days_until)
                next_sale = applicable_sales[0]
            else:
                # 적용 가능 여부 관계없이 가장 가까운 것
                all_sales.sort(key=lambda x: x.days_until)
                next_sale = all_sales[0]

        # 예상 절약 금액 계산 (wait 추천 상품들의 예상 할인 합계)
        potential_savings = 0
        for p in predictions:
            if p.buy_recommendation == "wait" and p.upcoming_sales:
                best_sale = max(p.upcoming_sales, key=lambda s: s.expected_discount if s.applicable else 0)
                if best_sale.applicable:
                    potential_savings += int(p.current_price * best_sale.expected_discount / 100)

        return PredictionSummary(
            total_products=len(predictions),
            buy_now_count=buy_now_count,
            wait_count=wait_count,
            neutral_count=neutral_count,
            next_sale=next_sale,
            potential_savings=potential_savings,
        )


# 싱글톤 인스턴스
_price_predictor: PricePredictor | None = None


def get_price_predictor() -> PricePredictor:
    """PricePredictor 싱글톤 인스턴스 반환"""
    global _price_predictor
    if _price_predictor is None:
        _price_predictor = PricePredictor()
    return _price_predictor
