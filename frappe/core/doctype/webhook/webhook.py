# -*- coding: utf-8 -*-
# Copyright (c) 2017, Frappe Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class Webhook(Document):
	def on_update(self):
		update_webhook_mapper()

def webhook_handler(doc, webhook_event):
	if not frappe.db.exists("DocType", "Webhook Service Event"):
		return

	events = frappe.cache().hget("webhook_events", doc.doctype)
	if not events:
		return

	for event in events:
		if event.get("document_event") != webhook_event or \
			event.get("document_name", None) != doc.doctype:
			continue

		frappe.enqueue('frappe.core.doctype.webhook.webhook.initiateREST', now=True, doc=doc,
			webhook_event=webhook_event, webhook=event.get("service"), resource_uri=event.get("resource_uri"))

def initiateREST(doc, webhook_event, webhook, resource_uri):
	auth = prepare_auth(webhook)
	if not auth:
		return

	method = get_method(webhook_event)
	if method:
		method(resource_uri)

def prepare_auth(webhook):
	webhook = frappe.db.get_value("Webhook", webhook, ["username", "password", "client_key", "client_secret",
		"resource_owner_key", "resource_owner_secret", "enabled", "authentication_type"], as_dict=1)

	if not webhook.enabled:
		return None

	if webhook.authentication_type == "Basic Authentication":
		return (webhook.username, webhook.password)

def get_method(event):
	from frappe.integrations.utils import make_post_request, make_put_request, make_delete_request

	return {
		'Create': make_post_request,
		"Save": make_put_request,
		"Submit": make_put_request,
		"Cancel": make_put_request,
		"Delete": make_delete_request
	}[event]

def update_webhook_mapper():
	""" create and cache webhook mapper """

	webhook_mapper = frappe._dict({})

	services = frappe.get_all("Webhook", filters={ "enabled": 1 },
		fields=["name"])

	if not services:
		frappe.cache().delete_key('webhook_events')
		return

	services = [ service.name for service in services ]

	webhook_events = frappe.get_all("Webhook Service Event", filters={
		"parent": ("in", services),
		"enabled": 1
	}, fields=["parent as service", "document_name", "resource_uri", "document_event"])

	for event in webhook_events:
		webhooks = webhook_mapper.get(event.document_name, [])
		webhooks.append(event)
		webhook_mapper.update({ event.document_name: webhooks })

	for document_name, events in webhook_mapper.iteritems():
		frappe.cache().hset('webhook_events', document_name, events)