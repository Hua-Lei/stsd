'''对 Access 模块公开读接口的适配。'''

from stsd.integration.access.project_versions import (
    AccessProjectVersionLookup,
)
from stsd.integration.access.projects import AccessProjectConfigLookup

__all__ = [
    'AccessProjectConfigLookup',
    'AccessProjectVersionLookup',
]
