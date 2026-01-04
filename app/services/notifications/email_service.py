"""
이메일 알림 서비스
카카오 알림톡 실패 시 fallback으로 사용
"""

import logging
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    """이메일 발송 서비스"""

    def __init__(self):
        settings = get_settings()
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_password = settings.smtp_password
        self.from_email = settings.smtp_from_email or settings.smtp_user
        self.enabled = bool(self.smtp_user and self.smtp_password)

    def is_available(self) -> bool:
        """이메일 서비스 사용 가능 여부"""
        return self.enabled

    async def send_price_alert(
        self,
        to_email: str,
        product_name: str,
        current_price: int,
        lowest_price: int,
        product_link: str,
        product_image: Optional[str] = None,
    ) -> bool:
        """
        가격 알림 이메일 전송

        Args:
            to_email: 수신자 이메일
            product_name: 상품명
            current_price: 현재 가격
            lowest_price: 90일 최저가
            product_link: 상품 링크
            product_image: 상품 이미지 URL (선택)

        Returns:
            전송 성공 여부
        """
        if not self.is_available():
            logger.warning("이메일 서비스가 설정되지 않았습니다")
            return False

        subject = f"🛒 CartPilot 최저가 알림: {product_name[:30]}..."

        # HTML 이메일 본문
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .product-card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .product-name {{ font-size: 18px; font-weight: 600; color: #333; margin-bottom: 15px; }}
                .price-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
                .price-label {{ color: #666; }}
                .current-price {{ font-size: 24px; font-weight: 700; color: #667eea; }}
                .lowest-price {{ font-size: 16px; color: #16a34a; }}
                .cta-button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: 600; margin-top: 20px; }}
                .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🛒 최저가 알림</h1>
                </div>
                <div class="content">
                    <p>안녕하세요! 관심 상품의 가격이 최저가에 도달했습니다.</p>

                    <div class="product-card">
                        <div class="product-name">{product_name}</div>

                        <div class="price-row">
                            <span class="price-label">현재 가격</span>
                            <span class="current-price">{current_price:,}원</span>
                        </div>

                        <div class="price-row">
                            <span class="price-label">90일 최저가</span>
                            <span class="lowest-price">{lowest_price:,}원</span>
                        </div>
                    </div>

                    <p style="text-align: center;">
                        <a href="{product_link}" class="cta-button">상품 보러가기 →</a>
                    </p>
                </div>
                <div class="footer">
                    <p>이 메일은 CartPilot 가격 알림 서비스에서 발송되었습니다.</p>
                    <p>© 2024 CartPilot. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # 일반 텍스트 버전
        text_content = f"""
        CartPilot 최저가 알림

        상품명: {product_name}
        현재 가격: {current_price:,}원
        90일 최저가: {lowest_price:,}원

        상품 링크: {product_link}

        지금이 구매 적기입니다!
        """

        return await self._send_email(to_email, subject, text_content, html_content)

    async def send_custom_email(
        self,
        to_email: str,
        subject: str,
        text_content: str,
        html_content: Optional[str] = None,
    ) -> bool:
        """
        커스텀 이메일 전송

        Args:
            to_email: 수신자 이메일
            subject: 제목
            text_content: 텍스트 본문
            html_content: HTML 본문 (선택)

        Returns:
            전송 성공 여부
        """
        return await self._send_email(to_email, subject, text_content, html_content)

    async def send_welcome_notification(self, to_email: str) -> bool:
        """
        알림 설정 완료 환영 이메일 전송

        Args:
            to_email: 수신자 이메일

        Returns:
            전송 성공 여부
        """
        if not self.is_available():
            logger.warning("이메일 서비스가 설정되지 않았습니다")
            return False

        subject = "🛒 CartPilot 알림 설정이 완료되었습니다!"

        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }
                .container { max-width: 600px; margin: 0 auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }
                .header h1 { margin: 0; font-size: 24px; }
                .content { padding: 30px; }
                .feature-list { background-color: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0; }
                .feature-item { display: flex; align-items: center; margin: 12px 0; }
                .feature-icon { font-size: 20px; margin-right: 12px; }
                .feature-text { color: #333; }
                .footer { background-color: #f8f9fa; padding: 20px; text-align: center; color: #666; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 알림 설정 완료!</h1>
                </div>
                <div class="content">
                    <p>안녕하세요!</p>
                    <p>CartPilot 이메일 알림 설정이 완료되었습니다.<br>
                    이제 관심상품의 가격 변동 소식을 이메일로 받아보실 수 있습니다.</p>

                    <div class="feature-list">
                        <h3 style="margin-top: 0; color: #667eea;">알림을 받는 경우</h3>
                        <div class="feature-item">
                            <span class="feature-icon">📉</span>
                            <span class="feature-text">90일 최저가에 도달했을 때</span>
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">🎯</span>
                            <span class="feature-text">설정한 목표가에 도달했을 때</span>
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">⬇️</span>
                            <span class="feature-text">가격이 일정 비율 이상 하락했을 때</span>
                        </div>
                    </div>

                    <p style="color: #666;">관심상품에서 각 상품의 알림을 켜두시면 자동으로 알림을 보내드립니다.</p>
                </div>
                <div class="footer">
                    <p>이 메일은 CartPilot 가격 알림 서비스에서 발송되었습니다.</p>
                    <p>© 2024 CartPilot. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = """
        CartPilot 알림 설정 완료!

        안녕하세요!

        CartPilot 이메일 알림 설정이 완료되었습니다.
        이제 관심상품의 가격 변동 소식을 이메일로 받아보실 수 있습니다.

        알림을 받는 경우:
        - 90일 최저가에 도달했을 때
        - 설정한 목표가에 도달했을 때
        - 가격이 일정 비율 이상 하락했을 때

        관심상품에서 각 상품의 알림을 켜두시면 자동으로 알림을 보내드립니다.

        감사합니다.
        CartPilot 팀
        """

        return await self._send_email(to_email, subject, text_content, html_content)

    async def _send_email(
        self,
        to_email: str,
        subject: str,
        text_content: str,
        html_content: Optional[str] = None,
    ) -> bool:
        """실제 이메일 전송"""
        if not self.is_available():
            return False

        try:
            # 메시지 생성
            message = MIMEMultipart("alternative")
            message["From"] = self.from_email
            message["To"] = to_email
            message["Subject"] = subject

            # 텍스트 파트 추가
            text_part = MIMEText(text_content, "plain", "utf-8")
            message.attach(text_part)

            # HTML 파트 추가 (있는 경우)
            if html_content:
                html_part = MIMEText(html_content, "html", "utf-8")
                message.attach(html_part)

            # 비동기 SMTP 전송
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                start_tls=True,
                username=self.smtp_user,
                password=self.smtp_password,
            )

            logger.info(f"이메일 전송 성공: {to_email}")
            return True

        except Exception as e:
            logger.error(f"이메일 전송 실패: {e}")
            return False


# 싱글톤 인스턴스
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """이메일 서비스 싱글톤 반환"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
