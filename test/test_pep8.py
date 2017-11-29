
import os
import unittest
import pep8


class PackagePep8TestCase(unittest.TestCase):

    def test_pep8(self):
        basepath = os.path.abspath(
            os.path.join(os.path.dirname(__file__), ".."))
        style = pep8.StyleGuide(quiet=True)
        res = style.check_files(paths=[basepath]).total_errors
        self.assertEqual(res, 0)


if __name__ == "__main__":
    unittest.main()
