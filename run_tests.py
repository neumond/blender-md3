import sys
sys.path.extend(eval(sys.argv[-1]))

import pytest
exit_code = pytest.main([])
with open('result.txt', 'w') as f:
    f.write(str(exit_code))
