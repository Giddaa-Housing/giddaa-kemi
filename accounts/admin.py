from django.contrib import admin

from accounts import models


class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'username', 'phone']


class OrganizationProfileAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'bio', 'city', 'address', 'country', 'zip_code',
        'phone', 'email', 'website', 'subscription_start', 'subscription_end', 'subscription_plan',
        'industry', 'size',
    ]


class OrganizationCustomerAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'role', 
    ]


admin.site.register(models.User, UserAdmin)
admin.site.register(models.OrganizationProfile, OrganizationProfileAdmin)
admin.site.register(models.OrganizationCustomer, OrganizationCustomerAdmin)
