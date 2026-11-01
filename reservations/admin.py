from django.contrib import admin
from .models import Venue, Reservation, UserProfile, VenueClosure


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'role', 'phone', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email', 'phone')


@admin.register(VenueClosure)
class VenueClosureAdmin(admin.ModelAdmin):
    list_display = ('id', 'venue', 'start_time', 'end_time', 'reason', 'created_at')
    list_filter = ('venue', 'start_time')
    search_fields = ('venue__name', 'reason')


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'location', 'capacity', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'location', 'description')


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'venue', 'user', 'start_time', 'end_time', 'status', 'created_at')
    list_filter = ('status', 'venue', 'start_time')
    search_fields = ('venue__name', 'user__username', 'reason')
    date_hierarchy = 'start_time'
