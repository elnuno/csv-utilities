import csv
import io
import datetime


DEFAULT_DECODING_ERRORS = 'strict'
DEFAULT_FIELD_DELIMITER = '\t'  # csv default is ','
DEFAULT_LINE_DELIMITER = '\n'  # csv ignores this, \n and \r are hard-coded
DEFAULT_STRICTDELIMITATION = False
DEFAULT_QUOTE_CHAR = '"'
DEFAULT_QUOTING = csv.QUOTE_MINIMAL
DEFAULT_SKIPINITIALSPACE = True  # csv default is False
DEFAULT_TIME_FORMAT = r'%H:%M:%S.%f'
DEFAULT_DATE_FORMAT = r'%Y-%m-%d'
DEFAULT_DATETIME_FORMAT = r'%Y-%m-%d %H:%M:%S.%f'


# converts a string to a specific type
def _convert(text, new_type, new_format, raise_on_error):
    try:
        stripped_text = text.strip(' ')
        if stripped_text == '':
            return None
        elif new_type == 'string':
            return stripped_text
        elif new_type == 'integer':
            return int(stripped_text)
        elif new_type == 'float':
            return float(stripped_text)
        elif new_type == 'date':
            return datetime.datetime.date(
                       datetime.datetime.strptime(stripped_text, new_format))
        elif new_type == 'datetime':
            return datetime.datetime.strptime(stripped_text, new_format)
        else:
            return stripped_text
    except ValueError:  # trap only conversion errors, nothing else
        if raise_on_error:
            raise
        else:
            return None


# This class is a convenience wrapper around the standard 'csv' module for
# iterating over the lines in a delimited file.  It's behavior can be controlled
# with the following parameters:
#  fields:
#    a list of field information, each element contains the name, datatype
#    and format of that field
#  encoding: the encoding of the file
#  decoding_errors: what to do with decoding errors
#  delimiter: the field delimiter character
#  quote_char: the character that may optionally bookend field values
#  strict_delimitation:
#    if False, some attempts will be made to correct delimitation errors in
#    the file
#  number_of_header_lines: header lines will be skipped by this class
#  convert_values:
#    if True, the field values will be converted to Python objects before
#    being returned
#  raise_convert_errors:
#    if False, fields that cannot be converted will be replaced (silently) with
#    None, otherwise a ValueError exception will be raised and processing of
#    the file will stop
#  rpad:
#    causes each line to be filled out to its full length if the line has fewer
#    fields than expected
#  The 'rows_read' attribute does not include header line(s).
#
# Example of use:
#   with Reader(my_filename, my_fields) as reader:
#       print('first line: {}'.format(next(reader)))
#       reader.reset()
#       for row in reader:
#           print('line number {}: {}'.format(reader.rows_read, row))
#
class Reader:

    def __init__(self, filename, fields,
                 encoding=None, decoding_errors=None, delimiter=DEFAULT_FIELD_DELIMITER,
                 quote_char=DEFAULT_QUOTE_CHAR, strict_delimitation=DEFAULT_STRICTDELIMITATION,
                 number_of_header_lines=0, convert_values=False, raise_convert_errors=True, rpad=False):

        self.filename = filename
        self.fields = fields.copy()
        self.encoding = encoding
        self.delimiter = delimiter
        self.quote_char = quote_char
        self.strict_delimitation = strict_delimitation
        self.number_of_header_lines = number_of_header_lines
        self.decoding_errors = decoding_errors
        self.convert_values = convert_values
        self.raise_convert_errors = raise_convert_errors
        self.rpad = rpad

        self.file = None
        self.reader = None
        self._rows_read = None

        self._len_fields = len(self.fields)
        self._field_types = []
        self._field_formats = []
        self._max_index = -1
        for field in self.fields:
            self._field_types.append(field.get('datatype', 'string'))
            if field.get('datatype') == 'date':
                self._field_formats.append(field.get('date_format', DEFAULT_DATE_FORMAT))
            elif field.get('datatype') == 'datetime':
                self._field_formats.append(field.get('datetime_format', DEFAULT_DATETIME_FORMAT))
            else:
                self._field_formats.append(None)
            self._max_index += 1

    def __enter__(self):
        return self

    def __iter__(self):
        if self.file is None:
            self._open()
        return self

    def _process(self, line):
        """Massage data before feeding it to csv.reader."""
        return line.replace('\0', ' ')

    def _open(self):
        _process = self._process
        self.file = open(self.filename, 'r',
                         encoding=self.encoding,
                         errors=DEFAULT_DECODING_ERRORS if self.decoding_errors is None else self.decoding_errors,
                         newline=None)
        # csv breaks if it encounters a null character
        self.reader = csv.reader((_process(line) for line in self.file),
                                 delimiter=self.delimiter,
                                 strict=self.strict_delimitation,
                                 quotechar=self.quote_char,
                                 quoting=csv.QUOTE_NONE if self.quote_char is None else DEFAULT_QUOTING,
                                 skipinitialspace=DEFAULT_SKIPINITIALSPACE)
        self._rows_read = 0
        for index in range(self.number_of_header_lines):
            next(self.file)

    # a StopIteration exception occurs on the call to next() if there's no more data
    def __next__(self):

        if self.file is None:
            self._open()

        if self.convert_values:

            row = next(self.reader)
            if len(row) <= self._len_fields:
                line = [_convert(*z, raise_on_error=self.raise_convert_errors)
                        for z in zip(row, self._field_types, self._field_formats)]
                if self.rpad:
                    line += [None] * (self._len_fields - len(line))
            else:
                line = [_convert(*z, raise_on_error=self.raise_convert_errors)
                        for z in zip(row, self._field_types, self._field_formats)] + \
                       [_convert(f, 'string', None, raise_on_error=self.raise_convert_errors)
                        for f in row[self._len_fields:]]

        else:

            line = next(self.reader)
            if self.rpad and len(line) < self._len_fields:
                line += [''] * (self._len_fields - len(line))

        self._rows_read += 1
        return line

    # return to the start of the file, just before the first non-header line
    def reset(self):
        if self.file is None:
            self._open()
        else:
            self.file.seek(0)
            self._rows_read = 0
            for index in range(self.number_of_header_lines):
                next(self.file)

    def __exit__(self, exc_type, exc_value, traceback):
        if self.file is not None:
            self._close()

    def _close(self):
        self.reader = None
        self.file.close()
        self.file = None

    @property
    def rows_read(self):
        return self._rows_read


class NoMultilineQuotedReader(Reader):
    def _process(self, line):
        """Handle dangling quote characters before passing to csv.reader."""
        line = line.replace('\0', ' ')
        quote = self.quote_char
        if not quote:
            return line

        # In the worst case, we scan the string to count chars/sequences five
        # times. It might pay off to count all possible interesting substrings
        # in a single pass, but it doesn't seem too promising.
        count = line.count(quote)
        if not count:
            return line

        delimiter = self.delimiter
        escape = '\\'
        dangling_quote = False

        # Here we go. While the general idea of checking whether there
        # are balanced quotes, escaped quotes, etc. seems inviting, it might
        # only be a red herring: all paths seem to converge to parsing in
        # the end. So we use csv.reader to parse a single line, then
        # normalize it by calling csv.writer.writerow.

        if escape not in line:
            # We have no escaped quotes. Let's figure out how many are
            # easy valid quotes (as opposed to possibly dangling ones).
            postfix = line.count(quote + delimiter)
        else:
            escaped = line.count(escape + quote)
            if escaped == count:  # All quotes are escaped, we're done
                return line
            escaped_postfix = line.count(escape + quote + delimiter)
            postfix = line.count(quote + delimiter) - escaped_postfix
        if postfix == count:
            # All non-escaped quotes appear right before a delimiter, a valid
            # position: 'a,b",c' -> ['a', 'b"', 'c']
            return line

        # We couldn't bail out. So let's parse the line with a new reader
        # and use that to normalize it.

        # Striping leading/trailing newline/spaces might not be the best here.
        # Adjust tests to desired behavior when it's decided upon.
        line = line.strip()
        reader = csv.reader((line,), delimiter=self.delimiter,
                strict=self.strict_delimitation, quotechar=self.quote_char,
                quoting=csv.QUOTE_NONE if self.quote_char is None
                else DEFAULT_QUOTING,
                skipinitialspace=DEFAULT_SKIPINITIALSPACE)
        parsed_line = next(reader)
        out = io.StringIO()
        dialect = reader.dialect
        writer = csv.writer(out, dialect)
        writer.writerow(parsed_line)
        line = out.getvalue()

        return line
