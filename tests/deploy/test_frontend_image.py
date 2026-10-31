"""The frontend image's nginx config gets every value it needs from the image itself.

At startup the nginx image renders frontend/nginx/default.conf.template, and it substitutes only
variables that are set. An unset one stays in the config as literal text, nginx refuses to start,
and every page goes down. The release workflow also starts the image before publishing it.
"""

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
# The nginx image's entrypoint exports these when the flag beside them is set.
SET_BY_THE_ENTRYPOINT = {"NGINX_LOCAL_RESOLVERS": "NGINX_ENTRYPOINT_LOCAL_RESOLVERS"}


def _template_variables() -> set[str]:
    template = (FRONTEND / "nginx" / "default.conf.template").read_text()
    return set(re.findall(r"\$\{(\w+)\}", template))


def _final_stage_env() -> set[str]:
    """Names set by ENV in the Dockerfile's last stage, the one the image runs."""
    dockerfile = (FRONTEND / "Dockerfile").read_text().replace("\\\n", " ")
    final_stage = re.split(r"^FROM\s", dockerfile, flags=re.MULTILINE)[-1]
    env_lines = (line for line in final_stage.splitlines() if line.startswith("ENV "))
    return {name for line in env_lines for name in re.findall(r"(\w+)=", line)}


def test_every_template_variable_is_set_in_the_image() -> None:
    env = _final_stage_env()
    provided = env | {name for name, flag in SET_BY_THE_ENTRYPOINT.items() if flag in env}

    assert _template_variables() - provided == set()
