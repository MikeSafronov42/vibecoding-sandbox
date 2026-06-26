import calendar

# Create a plain text calendar
c = calendar.TextCalendar(calendar.MONDAY)
str = c.formatmonth(2015, 7)
print(str)