# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------


import unittest
import nmcliparse


class TestParser(unittest.TestCase):

    def test_basic(self):
        tokenlist = nmcliparse.parse_output_line("one:two:three")
        self.assertEquals(len(tokenlist), 3)
        self.assertEquals(tokenlist[0], "one")
        self.assertEquals(tokenlist[1], "two")
        self.assertEquals(tokenlist[2], "three")

    def test_two_empty_tokens_out_of_three(self):
        tokenlist = nmcliparse.parse_output_line("::three")
        self.assertEquals(len(tokenlist), 3)
        self.assertEquals(tokenlist[0], "")
        self.assertEquals(tokenlist[1], "")
        self.assertEquals(tokenlist[2], "three")

    def test_two_empty_tokens(self):
        tokenlist = nmcliparse.parse_output_line(":")
        self.assertEquals(len(tokenlist), 2)
        self.assertEquals(tokenlist[0], "")
        self.assertEquals(tokenlist[1], "")

    def test_first_token_is_a_colon(self):
        tokenlist = nmcliparse.parse_output_line("\::two:three")
        self.assertEquals(len(tokenlist), 3)
        self.assertEquals(tokenlist[0], ":")
        self.assertEquals(tokenlist[1], "two")
        self.assertEquals(tokenlist[2], "three")

    def test_last_token_is_a_colon(self):
        tokenlist = nmcliparse.parse_output_line("one:two:\:")
        self.assertEquals(len(tokenlist), 3)
        self.assertEquals(tokenlist[0], "one")
        self.assertEquals(tokenlist[1], "two")
        self.assertEquals(tokenlist[2], ":")

    def test_middle_token_is_a_colon(self):
        tokenlist = nmcliparse.parse_output_line("one:\::three")
        self.assertEquals(len(tokenlist), 3)
        self.assertEquals(tokenlist[0], "one")
        self.assertEquals(tokenlist[1], ":")
        self.assertEquals(tokenlist[2], "three")

    def test_token_ends_with_colon(self):
        tokenlist = nmcliparse.parse_output_line("one:two\::three")
        self.assertEquals(len(tokenlist), 3)
        self.assertEquals(tokenlist[0], "one")
        self.assertEquals(tokenlist[1], "two:")
        self.assertEquals(tokenlist[2], "three")

    def test_token_starts_with_colon(self):
        tokenlist = nmcliparse.parse_output_line("one:\:two:three")
        self.assertEquals(len(tokenlist), 3)
        self.assertEquals(tokenlist[0], "one")
        self.assertEquals(tokenlist[1], ":two")
        self.assertEquals(tokenlist[2], "three")

    def test_no_tokens(self):
        tokenlist = nmcliparse.parse_output_line("")
        self.assertEquals(len(tokenlist), 0)

    def test_one_token(self):
        tokenlist = nmcliparse.parse_output_line("one")
        self.assertEquals(len(tokenlist), 1)
        self.assertEquals(tokenlist[0], "one")

    def test_one_token_with_lots_of_colons(self):
        tokenlist = nmcliparse.parse_output_line("\:\:\:\:\:")
        self.assertEquals(len(tokenlist), 1)
        self.assertEquals(tokenlist[0], ":::::")


if __name__=='__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestParser)
    unittest.TextTestRunner(verbosity=2).run(suite)

