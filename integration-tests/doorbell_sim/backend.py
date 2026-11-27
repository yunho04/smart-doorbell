"""Spring 백엔드 기동 관리와 "실제 LLM 으로 요청이 나가지 않는가" 안전 점검."""
import os
import signal
import subprocess
import time

from .settings import BACKEND_DIR, LOG_DIR, TEST_PROPS


def listener_pid(port):
    try:
        out = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
                             capture_output=True, text=True, timeout=5).stdout.split()
        return int(out[0]) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def uses_test_config(pid):
    """실행 중인 백엔드가 통합 테스트 설정(가상 LLM 주소)으로 떠 있는지 프로세스 인자로 확인한다."""
    try:
        command = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                 capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return TEST_PROPS.name in command


class Backend:
    def __init__(self, api, port):
        self.api, self.port, self.process, self.log_path = api, port, None, LOG_DIR / "backend.log"

    def start(self, timeout=240):
        LOG_DIR.mkdir(exist_ok=True)
        env = dict(os.environ)
        if "JAVA_HOME" not in env:   # build.gradle 의 toolchain 이 JDK 21 이므로 있으면 그것으로 Gradle 을 띄운다
            try:
                home = subprocess.run(["/usr/libexec/java_home", "-v", "21"], capture_output=True, text=True).stdout.strip()
                if home:
                    env["JAVA_HOME"] = home
            except OSError:
                pass
        # --args 는 공백으로 나뉘므로 저장소 경로에 공백이 있으면 README 의 수동 실행 방법을 쓴다.
        args = "--args=--spring.config.additional-location=file:%s" % TEST_PROPS
        with open(self.log_path, "w") as log:
            self.process = subprocess.Popen(["./gradlew", "bootRun", args], cwd=BACKEND_DIR, env=env,
                                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.api.is_up():
                return True
            if self.process.poll() is not None:
                return False
            time.sleep(1)
        return False

    def stop(self):
        if self.process is None:
            return
        pid = listener_pid(self.port)
        if pid and uses_test_config(pid):
            os.kill(pid, signal.SIGTERM)      # Spring JVM 정상 종료
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGTERM)
