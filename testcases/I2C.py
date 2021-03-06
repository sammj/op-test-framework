#!/usr/bin/python2
# IBM_PROLOG_BEGIN_TAG
# This is an automatically generated prolog.
#
# OpenPOWER Automated Test Project
#
# Contributors Listed Below - COPYRIGHT 2015,2017
# [+] International Business Machines Corp.
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.
#
# IBM_PROLOG_END_TAG

#  I2C driver to support openpower platform
#
#  This class will test functionality of following drivers
#  I2C Driver(Inter-Integrated Circuit) driver
#
#

import time
import subprocess
import re
import sys

from common.OpTestConstants import OpTestConstants as BMC_CONST

import unittest

import OpTestConfiguration
from common.OpTestUtil import OpTestUtil
from common.OpTestSystem import OpSystemState
from common.Exceptions import CommandFailed, KernelModuleNotLoaded, KernelConfigNotSet
class I2CDetectUnsupported(Exception):
    """Asked to do i2c detect on a bus that doesn't support detection
    """
    pass

class I2C():
    def setUp(self):
        conf = OpTestConfiguration.conf
        self.cv_HOST = conf.host()
        self.cv_IPMI = conf.ipmi()
        self.cv_SYSTEM = conf.system()
        self.util = OpTestUtil()

    def set_up(self):
        if self.test == "skiroot":
            self.cv_SYSTEM.goto_state(OpSystemState.PETITBOOT_SHELL)
            self.c = self.cv_SYSTEM.sys_get_ipmi_console()
            self.cv_SYSTEM.host_console_unique_prompt()
        elif self.test == "host":
            self.cv_SYSTEM.goto_state(OpSystemState.OS)
            self.c = self.cv_HOST.get_ssh_connection()
        else:
            raise Exception("Unknow test type")
        return self.c

    def i2c_init(self):
        self.cv_HOST.host_get_OS_Level()

        # make sure install "i2c-tools" package in-order to run the test

        # Check whether i2cdump, i2cdetect and hexdump commands are available on host
        self.cv_HOST.host_check_command("i2cdump", "i2cdetect", "hexdump",
                                        "i2cget", "i2cset")

        # Get Kernel Version
        l_kernel = self.cv_HOST.host_get_kernel_version()

        mods = {"CONFIG_I2C_OPAL": "i2c_opal",
                "CONFIG_I2C_CHARDEV": "i2c_dev",
                "CONFIG_EEPROM_AT24": "at24"
            }

        try:
            for (c,m) in mods.items():
                self.cv_HOST.host_load_module_based_on_config(l_kernel, c, m)
        except KernelConfigNotSet as ns:
            self.assertTrue(False, str(ns))
        except KernelModuleNotLoaded as km:
            if km.module == "at24":
                pass # We can fail if we don't load it, not all systems have it
            else:
                self.assertTrue(False, str(km))

        # Get information of EEPROM chips
        eeprom_info = self.host_get_info_of_eeprom_chips()
        if self.cv_SYSTEM.has_host_accessible_eeprom():
            self.assertNotEqual(eeprom_info, None)
        else:
            self.assertEqual(eeprom_info, None)

    ##
    # @brief This function will return the list of installed i2c buses on host in two formats
    #        list-by number Ex: ["0","1","2",....]
    #        list-by-name  Ex: ["i2c-0","i2c-1","i2c-2"....]
    #
    # @return l_list @type list: list of i2c buses by number
    #         l_list1 @type list: list of i2c buses by name
    #         or raise OpTestError if not able to get list of i2c buses
    #
    def host_get_list_of_i2c_buses(self):
        self.c.run_command("i2cdetect -l")
        l_res = self.c.run_command("i2cdetect -l | awk '{print $1}'")
        # list by number Ex: ["0","1","2",....]
        l_list = []
        # list by name Ex: ["i2c-0","i2c-1"...]
        l_list1 = []
        for l_bus in l_res:
            matchObj = re.search("(i2c)-(\d{1,})", l_bus)
            if matchObj:
                l_list.append(matchObj.group(2))
                l_list1.append(l_bus)
            else:
                pass
        return l_list, l_list1


    ##
    # @brief It will return list with elements having pairs of eeprom chip addresses and
    #        corresponding i2c bus where the chip is attached. This information is getting
    #        through sysfs interface. format is ["0 0x50","0 0x51","1 0x51","1 0x52"....]
    #
    # @return l_chips @type list: list having pairs of i2c bus number and eeprom chip address.
    #           else raise OpTestError
    #
    def host_get_list_of_eeprom_chips(self):
        l_res = self.c.run_command("find /sys/ -name eeprom")
        l_chips = []
        for l_line in l_res:
            if l_line.__contains__("eeprom"):
                matchObj = re.search("/(\d{1,}-\d{4})/eeprom", l_line)
                if matchObj:
                    l_line = matchObj.group(1)
                    i_args = (l_line.replace("-", " "))
                    print i_args
                else:
                    continue
                i_args = re.sub(" 00", " 0x", i_args)
                l_chips.append(i_args)
                print i_args
        return l_chips

    ##
    # @brief This function will get information of EEPROM chips attached to the i2c buses
    #
    # @return l_res @type string: return EEPROM chips information
    #           else raise OpTestError
    #
    def host_get_info_of_eeprom_chips(self):
        print "Getting the information of EEPROM chips"
        l_res = None
        try:
            l_res = self.c.run_command("cat /sys/bus/i2c/drivers/at24/*/name")
        except CommandFailed as cf:
            l_res = self.c.run_command("dmesg -C")
            try:
                self.c.run_command("rmmod at24")
                self.cv_HOST.host_load_module("at24")
                l_res = self.c.run_command("cat /sys/bus/i2c/drivers/at24/*/name")
            except CommandFailed as cf:
                pass
            except KernelModuleNotLoaded as km:
                pass
        return l_res

    ##
    # @brief The hexdump utility is used to display the specified files.
    #        This function will display in both ASCII+hexadecimal format.
    #
    # @param i_dev @type string: this is the file used as a input to hexdump for display info
    #                            Example file:"/sys/devices/platform/3fc0000000000.xscom:i2cm@a0000:i2c-bus@1/i2c-3/3-0050/eeprom"
    #
    # @return BMC_CONST.FW_SUCCESS or raise OpTestError
    #
    #
    def host_hexdump(self, i_dev):
        l_res = self.c.run_command("hexdump -C %s" % i_dev)


    ##
    # @brief This function query's the i2c bus for devices attached to it.
    #        i2cdetect is a utility to scan an I2C bus for devices
    #
    # @param i_bus @type string: i2c bus numer
    #
    # @return BMC_CONST.FW_SUCCESS or raise OpTestError
    #
    def query_i2c_bus(self, i_bus):
        rc = 0
        print "Querying the i2c bus %s for devices attached to it" % i_bus
        try:
            l_res = self.c.run_command("i2cdetect -y %i" % int(i_bus))
        except CommandFailed as cf:
            rc = cf.exitcode

        if rc != 0:
            try:
                l_res = self.c.run_command("i2cdetect -F %i|egrep '(Send|Receive) Bytes'|grep yes" % int(i_bus))
            except CommandFailed as cf:
                print "i2c bus %i doesn't support query" % int(i_bus)
                raise I2CDetectUnsupported;

            try:
                l_res = self.c.run_command("i2cdetect -y -r %i" % int(i_bus))
            except CommandFailed as cf:
                self.assertEqual(cf.exitcode, 0, "Querying the i2cbus for devices failed:%s\n%s" % (i_bus,str(cf)))

    ##
    # @brief This i2cdump function takes arguments in pair of a string like "i2cbus address".
    #        i2cbus indicates the number or name of the I2C bus to be scanned. This number should
    #        correspond  to  one  of  the busses listed by i2cdetect -l. address indicates
    #        the address to be scanned on that bus, and is an integer between 0x03 and 0x77
    #        i2cdump is a program to examine registers visible through the I2C bus
    #
    # @param i_args @type string: this is the argument to i2cdump utility
    #                             args are in the form of "i2c-bus-number eeprom-chip-address"
    #                             Ex: "0 0x51","3 0x52" ....etc
    #
    # @return BMC_CONST.FW_SUCCESS or raise OpTestError
    #
    def i2c_dump(self, i_args):
        try:
            l_res = self.c.run_command("i2cdump -f -y %s" % i_args)
        except CommandFailed as cf:
            self.assertEqual(cf.exitcode, 0, "i2cdump failed for the device: %s\n%s" % (i_args, str(cf)))

    ##
    # @brief This function i2cget read from I2C/SMBus chip registers
    #        command usage: i2cget [-f] [-y] i2cbus chip-address [data-address [mode]]
    #
    # @param i_args @type string: this is the argument to i2cget utility
    #                             args are in the form of "i2c-bus-number eeprom-chip-address"
    #                             Ex: "0 0x51","3 0x52" ....etc
    # @param i_addr @type string: this is the data-address on chip, from where data will be read
    #                             Ex: "0x00","0x10","0x20"...
    #
    # @return l_res @type string: data present on data-address or raise OpTestError
    #
    def i2c_get(self, i_args, i_addr):
        try:
            l_res = self.c.run_command("i2cget -f -y %s %s" % (i_args, i_addr))
        except CommandFailed as cf:
            self.assertEqual(cf.exitcode, 0, "i2cget: Getting data from address %s failed: %s" % (i_addr, str(cf)))

    ##
    # @brief This function i2cset will be used for setting I2C registers
    #        command usage: i2cset [-f] [-y] [-m mask] [-r] i2cbus chip-address data-address [value] ...  [mode]
    #
    # @param i_args @type string: this is the argument to i2cset utility
    #                             args are in the form of "i2c-bus-number eeprom-chip-address"
    #                             Ex: "0 0x51","3 0x52" ....etc
    # @param i_addr @type string: this is the data-address on chip, where data will be set
    #                             Ex: "0x00","0x10","0x20"...
    # @param i_val @type string: this is the value which will be set into data-address i_addr
    #
    # @return BMC_CONST.FW_SUCCESS or raise OpTestError
    #
    def i2c_set(self, i_args, i_addr, i_val):
        try:
            l_res = self.c.run_command("i2cset -f -y %s %s %s" % (i_args, i_addr, i_val))
        except CommandFailed as cf:
            self.assertEqual(cf.exitcode, 0, "i2cset: Setting the data to a address %s failed: %s" % (i_addr, str(cf)))

class FullI2C(I2C, unittest.TestCase):
    BASIC_TEST = False
    def setUp(self):
        self.test = "host"
        super(FullI2C, self).setUp()

    ##
    # @brief  This function has following test steps
    #         1. Getting host information(OS and kernel info)
    #         2. Checking the required utilites are present on host or not
    #         3. Loading the necessary modules to test I2C device driver functionalites
    #            (i2c_dev, i2c_opal and at24)
    #         4. Getting the list of i2c buses
    #         5. Querying the i2c bus for devices
    #         3. Getting the list of i2c buses and eeprom chip addresses
    #         4. Accessing the registers visible through the i2cbus using i2cdump utility
    #         5. Listing the i2c adapter conetents and i2c bus entries to make sure sysfs entries
    #            created for each bus.
    #         6. Testing i2cget functionality for limited samples
    #            Avoiding i2cset functionality, it may damage the system.
    def runTest(self):
        self.set_up()
        if self.test == "host":
            self.i2c_init()
        # Get list of i2c buses available on host,
        # l_list=["0","1"....]
        # l_list1=["i2c-0","i2c-1","i2c-2"....]
        l_list, l_list1 = self.host_get_list_of_i2c_buses()

        if self.BASIC_TEST:
            # For the basic test, just go for the first of everything.
            l_list = l_list[:1]
            l_list1 = l_list1[:1]

        # Scanning i2c bus for devices attached to it.
        for l_bus in l_list:
            try:
                self.query_i2c_bus(l_bus)
            except I2CDetectUnsupported:
                print "Unsupported i2cdetect on bus %s" % l_bus

        # Get list of pairs of i2c bus and EEPROM device addresses in the host
        l_chips = self.host_get_list_of_eeprom_chips()
        if self.cv_SYSTEM.has_host_accessible_eeprom():
            self.assertNotEqual(len(l_chips), 0, "No EEPROMs detected, while OpTestSystem says there should be")
            for l_args in l_chips:
                # Accessing the registers visible through the i2cbus using i2cdump utility
                # l_args format: "0 0x51","1 0x53",.....etc
                self.i2c_dump(l_args)
        else:
            self.assertEqual(len(l_chips), 0, "Detected EEPROM where OpTestSystem said there should be none")

        if self.cv_SYSTEM.has_host_accessible_eeprom():
            self.assertGreater(len(l_chips), 0, "Expected to find EEPROM chips")
            # Currently testing only getting the data from a data address,
            # avoiding setting data.
            # Only four samples are gathered to check whether reading eeprom
            # data is working or not.
            # Setting eeprom data is dangerous and make your system UNBOOTABLE
            l_addrs = ["0x00", "0x10", "0x20", "0x30", "0x40", "0x50", "0x60", "0x70", "0x80", "0x90", "0xa0", "0xb0", "0xc0", "0xd0", "0xe0", "0xf0"]
            for l_addr in l_addrs:
                l_val = self.i2c_get(l_chips[1], l_addr)
                # self.i2c_set(l_list2[1], l_addr, "0x50")

        # list i2c adapter conetents
        try:
            l_res = self.c.run_command("ls -l /sys/class/i2c-adapter")
        except CommandFailed as cf:
            self.assertEqual(cf.exitcode, 0, str(cf))

        # Checking the sysfs entry of each i2c bus
        for l_bus in l_list1:
            try:
                l_res = self.c.run_command("ls -l /sys/class/i2c-adapter/%s" % l_bus)
            except CommandFailed as cf:
                self.assertEqual(cf.exitcode, 0, str(cf))

        return BMC_CONST.FW_SUCCESS

class BasicI2C(FullI2C, unittest.TestCase):
    BASIC_TEST = True
    def setUp(self):
        self.test = "host"
        super(BasicI2C, self).setUp()


class BasicSkirootI2C(FullI2C, unittest.TestCase):
    BASIC_TEST = True
    def setUp(self):
        self.test = "skiroot"
        super(FullI2C, self).setUp()
