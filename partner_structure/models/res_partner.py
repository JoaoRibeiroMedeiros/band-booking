# © 2019 Akretion
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import ast
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import MissingError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

# TODO : allow translation of these structure types
STRUCTURE_TYPE = [("festival", "Festival"), ("venue", "Venue")]
STRUCTURE_CAPACITY = [
    ("inf1k", "< 1000"),
    ("sup1k", "> 1000"),
    ("sup5k", "> 5k"),
    ("sup10k", "> 10k"),
    ("sup30k", "> 30k"),
    ("sup100k", "> 100k"),
]


class Partner(models.Model):
    """Make the difference between classic Contacts and Structures (i.e. Venues and
    Festivals for the moment).
    Venues and Festivals will be linked to classic 'partners' and will display
    special fields about the Structure.
    """

    _inherit = "res.partner"

    def _get_structure_type_tags(self):
        struct_type_categ_type = self.env.ref(
            "partner_structure.structure_type_categ_type"
        )
        return self.env["res.partner.category"].search(
            [("category_type_id", "=", struct_type_categ_type.id,)]
        )

    def _get_structure_type(self):
        """ Check if the structure types have all their related tag with the same name
        and return them"""
        for struc_type in STRUCTURE_TYPE:
            if struc_type[0] not in [t.name for t in self._get_structure_type_tags()]:
                raise MissingError(
                    _(
                        """The Struture type {} is not related to any Tag.
                        It is necessary to add one before continuing.""".format(
                            struc_type[0]
                        )
                    )
                )
        return STRUCTURE_TYPE

    def _get_structure_capacity(self):
        return STRUCTURE_CAPACITY

    is_structure = fields.Boolean(help="Is a Festival or a Venue ?", store=True)

    # TODO (in v13) : Join structure_type and company_type with 'addselection'
    # Not possible before v13 because of the confusion between native
    # _compute_company_type and current onchange functions.
    structure_type = fields.Selection(
        selection=_get_structure_type,
        string="Structure Type",
        default=False,
        store=True,
    )

    structure_capacity = fields.Selection(
        selection=_get_structure_capacity,
        string="Structure Capacity",
        help="Average audience expected in this venue or festival",
    )

    struct_date_begin = fields.Date(
        string="Structure Date", help="The date on which the festival is used to start."
    )
    struct_date_end = fields.Date(string="Structure Date End")
    struct_short_date = fields.Char(string="Date", compute="_compute_struct_short_date")

    related_structure_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Related Structure",
        relation="rel_struct_partner",
        column1="related_partner_id",
        column2="related_structure_id",
        store=True,
    )
    related_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Related Contacts",
        relation="rel_struct_partner",
        column1="related_structure_id",
        column2="related_partner_id",
    )

    # Used structures names for Contacts tree view
    display_related_structure_names = fields.Char(
        "Related Structures",
        compute="_compute_display_related_structure_names",
        store=True,
        index=True,
    )
    # Used to display Tags in tree views
    display_category_ids = fields.Many2many(
        "res.partner.category",
        string="Tags for tree view",
        compute="_compute_display_category_ids",
    )

    facebook = fields.Char(help="Must begin by 'http://' to activate URL link")
    instagram = fields.Char(help="Must begin by 'http://' to activate URL link")

    # Compute lower stage_id for creating lead from partner
    lower_stage_id = fields.Many2one(
        "crm.stage", "Lower Lead Stage", compute="_compute_lower_stage_id"
    )

    # Compute leads number related to partner
    lead_count = fields.Integer("Leads", compute="_compute_lead_count")
    opp_done_count = fields.Integer("Done", compute="_compute_opp_done_count")
    opp_lost_count = fields.Integer("Lost", compute="_compute_opp_lost_count")

    # Confirmed partner ?
    is_confirmed = fields.Boolean(string="Confirmed", default=False)

    # Sequence integer to handle partner order in m2m tree views
    sequence = fields.Integer()

    @api.depends("struct_date_begin", "struct_date_end")
    def _compute_struct_short_date(self):
        """Display date in format DD/MM for Festivals tree view and CRM kanban view"""
        for partner in self:
            date_begin = partner.struct_date_begin
            date_end = partner.struct_date_end
            if date_begin:
                date_begin_obj = datetime.strptime(
                    str(date_begin), DEFAULT_SERVER_DATE_FORMAT
                )
                partner.struct_short_date = datetime.strftime(
                    date_begin_obj, "%d" + "/" + "%m"
                )
                if date_end and date_end != date_begin:
                    date_end_obj = datetime.strptime(
                        str(date_end), DEFAULT_SERVER_DATE_FORMAT
                    )
                    short_date_end = datetime.strftime(date_end_obj, "%d" + "/" + "%m")
                    partner.struct_short_date += " - " + short_date_end

    def toogle_confirmed(self):
        for partner in self:
            partner.is_confirmed = not partner.is_confirmed

    @api.depends("related_structure_ids")
    def _compute_display_related_structure_names(self):
        for partner in self:
            for structure in partner.related_structure_ids:
                if not partner.display_related_structure_names:
                    partner.display_related_structure_names = str(structure.name)
                else:
                    partner.display_related_structure_names += ", " + str(
                        structure.name
                    )

    def _compute_display_category_ids(self):
        """Display tags in tree view except special ones made to distinguish the type
        of Structure or Contact, like 'festival', 'venue' or 'partner' """
        for partner in self:
            special_type_tags = self.env["res.partner.category"].search(
                [("is_partner_type_categ", "=", True)]
            )
            partner.display_category_ids = partner.category_id - special_type_tags

    @api.onchange("related_structure_ids")
    def onchange_related_structure_ids(self):
        """Add or remove 'partner' tag if Contact related to structures"""
        for partner in [p for p in self if not p.is_structure]:
            if partner.related_structure_ids:
                partner.category_id |= self.env.ref("partner_structure.partner_tag")
            else:
                partner.category_id -= self.env.ref("partner_structure.partner_tag")

    # ---------------------------------------------------------------------
    # Onchange Relations between category_id, structure_type and company_type
    # ---------------------------------------------------------------------
    @api.onchange("category_id")
    def onchange_category_id(self):
        """Set structure_type dependind on Partner's tags"""

        for partner in self:
            if not partner.category_id:
                partner.structure_type = False
                partner.is_structure = False
            else:
                # Update structure_type depending on the structure_type's tags in the
                # current partner's tags
                stags_in_ptags = partner.category_id.filtered(
                    lambda tag: tag.category_type_id
                    == self.env.ref("partner_structure.structure_type_categ_type")
                )

                if len(stags_in_ptags) > 1:
                    # In this case, it means that the onchange added a structure_type's
                    # tag to another one already present in the partner's tags.
                    # So we delete the old one (i.e. the first one of the list)
                    # and match structure_type with the new one (i.e. the second one)
                    old_stag_id = stags_in_ptags[0]
                    partner.category_id = [(3, old_stag_id.id, 0)]
                    partner.structure_type = stags_in_ptags[1].name
                    partner.is_structure = True
                    partner.is_company = True
                elif len(stags_in_ptags) == 1:
                    # In this case, there was no structure_type's tag, so we just set
                    # the partner as a (new) structure
                    partner.structure_type = stags_in_ptags.name
                    partner.is_structure = True
                    partner.is_company = True
                else:
                    # No structure_type tag, so the partner can not be a Structure
                    partner.structure_type = False
                    partner.is_structure = False

    @api.onchange("structure_type")
    def onchange_structure_type(self):
        """Set related structure tag (i.e. the tag with the same name
        as structure_type's)"""
        self.ensure_one()
        # Remove current structure_type tags
        self.category_id -= self._get_structure_type_tags()

        if self.structure_type:
            self.is_structure = True
            self.is_company = True
            # Add selected structure_type tag
            self.category_id |= self.env["res.partner.category"].search(
                [("name", "=", "%s" % self.structure_type)]
            )

    @api.onchange("company_type")
    def onchange_company_type(self):
        for partner in self:
            if partner.company_type == "person":
                partner.is_company = False
                partner.structure_type = False
                partner.is_structure = False

    @api.onchange("is_structure")
    def onchange_is_structure(self):
        """Change Tags value and domain when switching from Structure to Contact and
        vice-versa"""
        # TODO : it would be awesome to also change dynamically the
        # 'default_category_type' CONTEXT in 'category_id' when switching from Structure
        # to Contact type
        if len(self) == 1:
            struc_tags_types = [
                self.env.ref("partner_structure.structure_categ_type").id,
                self.env.ref("partner_structure.structure_type_categ_type").id,
            ]
            contact_tags_types = [
                self.env.ref("partner_structure.contact_categ_type").id,
                self.env.ref("partner_structure.contact_type_categ_type").id,
            ]
            struc_tags_domain = [("category_type_id", "in", struc_tags_types)]
            contact_tags_domain = [("category_type_id", "in", contact_tags_types)]

            structure_tags = self.env["res.partner.category"].search(struc_tags_domain)
            contact_tags = self.env["res.partner.category"].search(contact_tags_domain)

            if self.is_structure:
                self.category_id &= structure_tags
                return {"domain": {"category_id": struc_tags_domain}}
            else:
                self.category_id &= contact_tags
                return {"domain": {"category_id": contact_tags_domain}}

    # ---------------------------------------------------------------------
    # Button to link (or create) leads from partner
    # ---------------------------------------------------------------------

    def _compute_lower_stage_id(self):
        """Find the Lead's stage_id with the lower sequence to create
        a lead from partner with this default stage"""
        stages = self.env["crm.stage"].search([])
        dict_sequences = {}
        for stage in stages:
            dict_sequences.setdefault(stage.id, stage.sequence)
        self.lower_stage_id = self.env["crm.stage"].browse(
            [min(dict_sequences, key=dict_sequences.get)]
        )

    def _compute_opportunity_count(self):
        """Override method do display a linked opportunity in partners related
        to a Structure with opportunity"""
        res = super(Partner, self)._compute_opportunity_count()
        for partner in self:
            if partner.is_structure:
                partner.opportunity_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "=", partner.id),
                        ("type", "=", "opportunity"),
                        (
                            "stage_id",
                            "!=",
                            self.env.ref("partner_structure.stage_done").id,
                        ),
                    ]
                )
            else:
                partner.opportunity_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "in", partner.related_structure_ids.ids),
                        ("type", "=", "opportunity"),
                        (
                            "stage_id",
                            "!=",
                            self.env.ref("partner_structure.stage_done").id,
                        ),
                    ]
                )

        return res

    def _compute_lead_count(self):
        """Identical method for counting related Leads"""
        for partner in self:
            if partner.is_structure:
                partner.lead_count = self.env["crm.lead"].search_count(
                    [("partner_id", "=", partner.id), ("type", "=", "lead")]
                )
            else:
                partner.lead_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "in", partner.related_structure_ids.ids),
                        ("type", "=", "lead"),
                    ]
                )

    def _compute_opp_done_count(self):
        """Count how many opportunities are in Stage which name is "Done" """
        for partner in self:
            if partner.is_structure:
                partner.opp_done_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "=", partner.id),
                        (
                            "stage_id",
                            "=",
                            self.env.ref("partner_structure.stage_done").id,
                        ),
                    ]
                )
            else:
                partner.opp_done_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "in", partner.related_structure_ids.ids),
                        (
                            "stage_id",
                            "=",
                            self.env.ref("partner_structure.stage_done").id,
                        ),
                    ]
                )

    def _compute_opp_lost_count(self):
        """Count how many opportunities were Lost (i.e. inactives with
        a null probability)"""
        for partner in self:
            if partner.is_structure:
                partner.opp_lost_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "=", partner.id),
                        ("probability", "=", 0),
                        ("active", "=", False),
                    ]
                )
            else:
                partner.opp_lost_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "in", partner.related_structure_ids.ids),
                        ("probability", "=", 0),
                        ("active", "=", False),
                    ]
                )

    def action_lead_from_partner(self):
        """Button's action to create a lead from a Structure partner"""
        self.ensure_one()

        xml_id = "crm.crm_lead_all_leads"
        action = self.env.ref(xml_id).read()[0]
        form = self.env.ref("crm.crm_case_form_view_leads")
        action["views"] = [(form.id, "form")]
        action["context"] = {
            "default_partner_id": self.id,
            "default_stage_id": self.lower_stage_id.id,
            "default_type": "lead",
        }

        return action

    def action_related_lead(self):
        """Display related Leads from Partner's smart button"""
        self.ensure_one()

        act_window_xml_id = "crm.crm_lead_all_leads"
        act_window = self.env.ref(act_window_xml_id).read()[0]

        if self.is_structure:
            domain = [("partner_id", "=", self.id), ("type", "=", "lead")]
        else:
            domain = [
                ("partner_id", "in", self.related_structure_ids.ids),
                ("type", "=", "lead"),
            ]

        act_window["domain"] = domain
        if self.lead_count == 1:
            form = self.env.ref("crm.crm_case_form_view_leads")
            act_window["views"] = [(form.id, "form")]
            act_window["res_id"] = self.env["crm.lead"].search(domain).id

        return act_window

    def action_related_opportunity(self):
        """Display related opportunities from Partner's smart button"""
        self.ensure_one()

        act_window_xml_id = "crm.crm_lead_opportunities"
        act_window = self.env.ref(act_window_xml_id).read()[0]

        if self.is_structure:
            domain = [
                ("partner_id", "=", self.id),
                ("stage_id", "!=", self.env.ref("partner_structure.stage_done").id),
                ("type", "=", "opportunity"),
            ]
        else:
            domain = [
                ("partner_id", "in", self.related_structure_ids.ids),
                ("stage_id", "!=", self.env.ref("partner_structure.stage_done").id),
                ("type", "=", "opportunity"),
            ]

        act_window["domain"] = domain
        if self.opportunity_count == 1:
            form = self.env.ref("crm.crm_case_form_view_oppor")
            act_window["views"] = [(form.id, "form")]
            act_window["res_id"] = self.env["crm.lead"].search(domain).id

        return act_window

    def action_done_opportunity(self):
        """Display Done opportunities from Partner's smart button"""
        self.ensure_one()

        act_window_xml_id = "crm.crm_lead_opportunities"
        act_window = self.env.ref(act_window_xml_id).read()[0]

        if self.is_structure:
            domain = [
                ("partner_id", "=", self.id),
                ("stage_id", "=", self.env.ref("partner_structure.stage_done").id),
            ]
        else:
            domain = [
                ("partner_id", "in", self.related_structure_ids.ids),
                ("stage_id", "=", self.env.ref("partner_structure.stage_done").id),
            ]

        act_window["domain"] = domain
        if self.opp_done_count == 1:
            form = self.env.ref("crm.crm_case_form_view_oppor")
            act_window["views"] = [(form.id, "form")]
            act_window["res_id"] = self.env["crm.lead"].search(domain).id

        return act_window

    def action_lost_opportunity(self):
        """Display Lost opportunities from Partner's smart button"""
        self.ensure_one()

        act_window_xml_id = "crm.crm_lead_opportunities"
        act_window = self.env.ref(act_window_xml_id).read()[0]

        if self.is_structure:
            domain = [
                ("partner_id", "=", self.id),
                ("probability", "=", 0),
                ("active", "=", False),
            ]
        else:
            domain = [
                ("partner_id", "in", self.related_structure_ids.ids),
                ("probability", "=", 0),
                ("active", "=", False),
            ]

        # act_window["context"] = {"search_default_lost": 1}
        act_window["domain"] = domain
        if self.opp_lost_count == 1:
            form = self.env.ref("crm.crm_case_form_view_oppor")
            act_window["views"] = [(form.id, "form")]
            act_window["res_id"] = self.env["crm.lead"].search(domain).id

        return act_window

    # ---------------------------------------------------------------------
    # Show period festival fields
    # ---------------------------------------------------------------------

    @api.constrains("struct_date_begin", "struct_date_end")
    def _check_closing_date(self):
        self.ensure_one()
        if self.struct_date_end and self.struct_date_begin:
            if self.struct_date_end < self.struct_date_begin:
                raise ValidationError(
                    _(
                        "The ending date cannot be earlier\
                    than the beginning date."
                    )
                )

    @api.onchange("struct_date_begin")
    def onchange_date_begin(self):
        """Pre-fill struct_date_end with struct_date_begin
        if no struct_date_end"""
        self.ensure_one()
        if not self.struct_date_end:
            self.struct_date_end = self.struct_date_begin

    # ---------------------------------------------------------------------
    # Add related_structure button
    # ---------------------------------------------------------------------

    # vvvvv TODO - WORK IN PROGRESS vvvvvvv
    #
    # def action_add_related_partner(self):
    #     """Button's action to add a new Partner to Many2many related_partner_ids
    #     in Structure field"""
    #     self.ensure_one()
    #
    #     xml_id = 'partner_structure.action_contacts'
    #     action = self.env.ref(xml_id).read()[0]
    #     # form = self.env.ref('partner_structure.view_partner_tree_contacts')
    #     # action['views'] = [(form.id, 'form')]
    #     action['target'] = 'new'
    #     # action['context'] = {'default_related_structure_ids' : self.}
    #
    #     return action

    # ---------------------------------------------------------------------
    # Method for custom Partner Autocomplete
    # ---------------------------------------------------------------------

    def _build_additional_contact(self, additional_info):
        """Build comment from additional emails and phone numbers"""
        comment = ""
        if len(additional_info.get("email")) > 1:
            comment += _("\n\nEmails :\n") + "\n".join(additional_info["email"][1:])
        if len(additional_info.get("phone_numbers")) > 1:
            comment += _("\n\nPhone numbers :\n") + "\n".join(
                additional_info["phone_numbers"][1:]
            )

        return comment

    # ---------------------------------------------------------------------
    # Propagate 'related_structure_ids' to Contact's childs and parents
    # ---------------------------------------------------------------------
    def propagate_related_struct(self):
        for partner in self:
            for p in partner.child_ids | partner.parent_id:
                if p.related_structure_ids != partner.related_structure_ids:
                    p.related_structure_ids = partner.related_structure_ids
                    # Add the partner_tag to all the propagated related contacts
                    p.category_id = [
                        (4, self.env.ref("partner_structure.partner_tag").id)
                    ]

    def write(self, vals):
        """ Add/Remove the partner_tag to new/old related Contacts and
        Propagate the partner's related structures from parent to childs"""
        # Catch the removed partners before saving the values
        removed_partners = self.env["res.partner"]
        if vals.get("related_partner_ids") and vals["related_partner_ids"][0][0] == 6:
            removed_partners = self.related_partner_ids - self.env[
                "res.partner"
            ].browse(vals["related_partner_ids"][0][2])

        # Change the values on self
        res = super().write(vals)
        for partner in self:
            if partner.is_structure:
                for rel_partner in partner.related_partner_ids:
                    # Add the partner_tag to all the related Contacts
                    rel_partner.category_id = [
                        (4, self.env.ref("partner_structure.partner_tag").id)
                    ]
                    # Add the childs and parent to the m2m
                    rel_partner.propagate_related_struct()
            else:
                partner.propagate_related_struct()
        # Remove the partner_tag on the removed contacts
        for partner in removed_partners:
            if not partner.related_structure_ids:
                partner.category_id = [
                    (3, self.env.ref("partner_structure.partner_tag").id)
                ]

        return res

    @api.model
    def create(self, vals):
        """Fill partner tags on creation following given context"""
        # TODO : We use this way to add the partner's tag overriding the create method
        # because we cannot do it by a classical ways like a
        # `context={'default_category_id': [(4, %(partner_structure.partner_tag)d)]}`
        # These kind of cache values will be erased by all the other compute and
        # onchange Partner's methods.
        # Thus this present solution is not ideal because it doesn't display the tag
        # during the creation... But it's better than nothing.
        tag_ids = []
        if vals["category_id"]:
            tag_ids += vals["category_id"][0][2]
        if self._context.get("partner_tag"):
            tag_ids.append(self.env.ref("partner_structure.partner_tag").id)
        vals["category_id"] = [(6, 0, set(tag_ids))]

        # Catch facebook and additional emails and phone numbers from the
        # module 'partner_autocomplete'
        # TODO : try to catch these additional info by overriding the 'enrich_company()'
        # in module 'partner_autocomplete' instead of overrinding the create in order to
        # fill the facebook and comment fields during the onchange
        if vals.get("additional_info"):
            additional_info = ast.literal_eval(
                vals["additional_info"].replace("false", "False")
            )
            if additional_info.get("facebook"):
                vals["facebook"] = (
                    "http://www.facebook.com/" + additional_info["facebook"]
                )
            vals["comment"] = self._build_additional_contact(additional_info)

        return super(Partner, self).create(vals)