"""A bunch of helper functions. """
import re
import sqlite3

date_regex = re.compile('\d\d\d\d-\d\d-\d\d')


def id_from_date_or_id(date_or_id: str, conn: sqlite3.Connection, is_public: bool = True):
    if bool(date_regex.match(date_or_id)):  # Then the user passed in a date
        cursor = conn.cursor()
        if is_public:
            cursor.execute('SELECT id, statement from problems where date = ? and public = ?', (date_or_id, True))
        else:
            cursor.execute('SELECT id, statement from problems where date = ?', (date_or_id,))

        result = cursor.fetchall()
        if len(result) == 0:
            raise Exception(f'There are no problems available for the date {date_or_id}. ')
        elif len(result) == 2:
            space = ' '

            # Get the id and first 10 letters of each problem.
            problems = ', '.join((f'{x[0]}: "{space.join(x[1].split(space)[:10])}..."' for x in result))
            raise Exception(f'There are multiple problems available for the date {date_or_id}: {problems}. ')
        else:
            # Return the unique ID.
            return result[0][0]
    elif date_or_id.isdecimal():
        potd_id = int(date_or_id)
        cursor = conn.cursor()
        if is_public:
            cursor.execute('SELECT EXISTS (SELECT id from problems where problems.id = ? and public = ? limit 1)',
                           (potd_id, True))
        else:
            cursor.execute('SELECT EXISTS (SELECT id from problems where problems.id = ? limit 1)', (potd_id,))
        if cursor.fetchall()[0][0]:
            return potd_id
        else:
            raise Exception(f'There are no problems available for the id {date_or_id}. ')
    else:
        raise Exception(f'Please enter a valid id or date. ')
