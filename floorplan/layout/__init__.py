from .base import LayoutEngine, ENGINES, register

# 导入所有引擎模块，触发 @register 装饰器注册
from . import aligned      # noqa: F401
from . import staggered    # noqa: F401
from . import herringbone  # noqa: F401
from . import five_board   # noqa: F401
from . import l_triple     # noqa: F401
