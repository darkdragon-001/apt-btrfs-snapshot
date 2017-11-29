
import os
import unittest
import pycodestyle


class PackagePycodestyleTestCase(unittest.TestCase):

    def test_pycodestyle(self):
        basepath = os.path.abspath(
            os.path.join(os.path.dirname(__file__), ".."))
        style = pycodestyle.StyleGuide(quiet=True)
        res = style.check_files(paths=[basepath]).total_errors
        self.assertEqual(res, 0)


if __name__ == "__main__":
    unittest.main()
