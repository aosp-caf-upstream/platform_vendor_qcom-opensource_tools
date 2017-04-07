# Copyright (c) 2012,2014-2015,2017 The Linux Foundation. All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 and
# only version 2 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from print_out import print_out_str
from parser_util import register_parser, RamParser
from mm import pfn_to_page, page_buddy, page_count, for_each_pfn


@register_parser('--print-pagetracking', 'print page tracking information (if available)')
class PageTracking(RamParser):

    def parse(self):
        if not self.ramdump.is_config_defined('CONFIG_PAGE_OWNER'):
            print_out_str('CONFIG_PAGE_OWNER not defined')
            return

        if (self.ramdump.kernel_version >= (3, 19, 0)):
            mem_section = self.ramdump.read_word('mem_section')

        trace_offset = 0
        nr_entries_offset = 0
        trace_entries_offset = 0
        offset = 0
        struct_holding_trace_entries = 0
        trace_entry_size = self.ramdump.sizeof("unsigned long")

        if (self.ramdump.kernel_version <= (3, 19, 0)):
            trace_offset = self.ramdump.field_offset('struct page', 'trace')
            nr_entries_offset = self.ramdump.field_offset(
                'struct stack_trace', 'nr_entries')
            trace_entries_offset = self.ramdump.field_offset(
                'struct page', 'trace_entries')
        else:
            page_ext_offset = self.ramdump.field_offset(
                                    'struct mem_section', 'page_ext')
            trace_offset = self.ramdump.field_offset(
                                    'struct page_ext', 'trace')
            trace_entries_offset = self.ramdump.field_offset(
                                'struct page_ext', 'trace_entries')
            nr_entries_offset = self.ramdump.field_offset(
                                'struct page_ext', 'nr_entries')
            mem_section_size = self.ramdump.sizeof("struct mem_section")
            page_ext_size = self.ramdump.sizeof("struct page_ext")

        out_tracking = self.ramdump.open_file('page_tracking.txt')
        out_frequency = self.ramdump.open_file('page_frequency.txt')
        sorted_pages = {}

        for pfn in for_each_pfn(self.ramdump):
            page = pfn_to_page(self.ramdump, pfn)
            order = 0

            """must be allocated, and the first pfn of an order > 0 page"""
            if (page_buddy(self.ramdump, page) or
                    page_count(self.ramdump, page) == 0):
                continue
            if (self.ramdump.kernel_version <= (3, 19, 0)):
                nr_trace_entries = self.ramdump.read_int(
                    page + trace_offset + nr_entries_offset)
                struct_holding_trace_entries = page
                order = self.ramdump.read_structure_field(
                            page, 'struct page', 'order')
            else:
                phys = pfn << 12
                if phys is None or phys is 0:
                    continue
                offset = phys >> 30

                mem_section_0_offset = (
                                mem_section + (offset * mem_section_size))
                page_ext = self.ramdump.read_word(
                            mem_section_0_offset + page_ext_offset)
                temp_page_ext = page_ext + (pfn * page_ext_size)
                nr_trace_entries = self.ramdump.read_int(
                                    temp_page_ext + nr_entries_offset)
                struct_holding_trace_entries = temp_page_ext
                order = self.ramdump.read_structure_field(
                            temp_page_ext, 'struct page_ext', 'order')

            if nr_trace_entries <= 0 or nr_trace_entries > 16:
                continue

            out_tracking.write('PFN 0x{:x}-0x{:x} page 0x{:x}\n'.format(
                pfn, pfn + (1 << order) - 1, page))

            alloc_str = ''
            for i in range(0, nr_trace_entries):
                addr = self.ramdump.read_word(
                    struct_holding_trace_entries + trace_entries_offset + i * trace_entry_size)

                if addr == 0:
                    break
                look = self.ramdump.unwind_lookup(addr)
                if look is None:
                    break
                symname, offset = look
                unwind_dat = '      [<{0:x}>] {1}+0x{2:x}\n'.format(
                                        addr, symname, offset)
                out_tracking.write(unwind_dat)
                alloc_str = alloc_str + unwind_dat

            if alloc_str in sorted_pages:
                sorted_pages[alloc_str] = sorted_pages[alloc_str] + 1
            else:
                sorted_pages[alloc_str] = 1

            out_tracking.write('\n')

        sortlist = sorted(sorted_pages.iteritems(),
                          key=lambda(k, v): (v), reverse=True)

        for k, v in sortlist:
            out_frequency.write('Allocated {0} times\n'.format(v))
            out_frequency.write(k)
            out_frequency.write('\n')

        out_tracking.close()
        out_frequency.close()
        print_out_str(
            '---wrote page tracking information to page_tracking.txt')
        print_out_str(
            '---wrote page frequency information to page_frequency.txt')
