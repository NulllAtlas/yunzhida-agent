            if not text:
                logger.warning("STT returned empty text")
                await self._send_error("未识别到语音，请再说一次")
                return