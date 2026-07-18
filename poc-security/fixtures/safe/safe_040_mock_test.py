from unittest.mock import Mock
m = Mock()
m.return_value = 42
m.side_effect = lambda x: x * 2
print(m(21))