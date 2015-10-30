# -*- coding: utf-8 -*-

# Copyright (c) 2015, Camptocamp SA
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies,
# either expressed or implied, of the FreeBSD Project.

"""internal and external layer tables refactoring, new ogc table

Revision ID: 116b9b79fc4d
Revises: 1418cb05921b
Create Date: 2015-10-28 12:21:59.162238
"""

from alembic import op, context
from sqlalchemy import ForeignKey, Column, Table, MetaData
from sqlalchemy.types import Integer, Boolean, Unicode, String, Float, \
    UserDefinedType, DateTime, Enum

# revision identifiers, used by Alembic.
revision = '116b9b79fc4d'
down_revision = '1418cb05921b'
branch_labels = None
depends_on = None


def upgrade():
    schema = context.get_context().config.get_main_option('schema')

    # Instructions
    op.create_table(
        'layer_ogc',
        Column('id', Integer, primary_key=True),
        Column('name', Unicode, nullable=False),
        Column('description', Unicode),
        Column('url', Unicode),
        # url_wfs needed for Arcgis because wms and wfs url may be different
        Column('url_wfs', Unicode),
        Column('type', Unicode),
        Column('image_type', Unicode),
        Column('auth', Unicode),
        Column('wfs_support', Boolean),
        schema=schema,
    )

    op.create_table(
        'layer_wms',
        Column(
            'id', Integer,
            ForeignKey(schema + '.layer.id'), primary_key=True
        ),
        Column(
            'layer_ogc_id', Integer,
            ForeignKey(schema + '.layer_ogc.id')
        ),
        Column('layer', Unicode),
        Column('style', Unicode),
        Column('is_single_tile', Boolean),
        Column('time_mode', Unicode, default=u'disabled', nullable=False),
        Column('time_widget', Unicode, default=u'slider', nullable=True),
        schema=schema,
    )

    # move data from layer_internal_wms and layer_external_wms to the new
    # layer_wms and layer_ogc tables

    # ocg for externals,
    # using the layer_external_wms.id as id to be able to keep link when
    # migrating the layer_wms table in the next step
    op.execute(
        "INSERT INTO %(schema)s.layer_ogc (id, name, url, image_type, auth) "
        "SELECT id, 'source for ' || layer, url, image_type, 'none' "
        "FROM %(schema)s.layer_external_wms" % {
            'schema': schema,
        }
    )
    # externals
    op.execute(
        "INSERT INTO %(schema)s.layer_wms (id, layer_ogc_id, layer, style, is_single_tile, time_mode, time_widget) "
        "SELECT id, id, layer, style, is_single_tile, time_mode, time_widget "
        "FROM %(schema)s.layer_external_wms" % {
            'schema': schema,
        }
    )

    # ocg for internal
    # default 'image/jpeg', 'image/png'
    op.execute(
        "INSERT INTO %(schema)s.layer_ogc (name, description, type, image_type, auth, wfs_support) "
        "SELECT 'source for ' || image_type AS name, 'default source for internal ' || image_type AS description, 'mapserver' AS type, image_type, 'main' AS auth, 'true' AS wfs_support "
        "FROM (SELECT UNNEST(ARRAY['image/jpeg', 'image/png']) AS image_type) AS foo" % {
            'schema': schema,
        }
    )
    # other custom image types, including NULL
    op.execute(
        "INSERT INTO %(schema)s.layer_ogc (name, description, type, image_type, auth, wfs_support) "
        "SELECT 'source for ' || "
        "CASE WHEN image_type IS NULL THEN 'undefined image_type' ELSE image_type END "
        "AS name, 'default source for internal ' || "
        "CASE WHEN image_type IS NULL THEN 'undefined image_type' ELSE image_type END "
        "AS description, 'mapserver' AS type, image_type, 'main' AS auth, 'true' AS wfs_support from ("
        "SELECT DISTINCT(image_type) FROM %(schema)s.layer_internal_wms "
        "WHERE image_type NOT IN ('image/jpeg', 'image/png') OR image_type IS NULL"
        ") as foo" % {
            'schema': schema,
        }
    )
    # internal with not null image_type
    op.execute(
        "INSERT INTO %(schema)s.layer_wms (id, layer_ogc_id, layer, style, time_mode, time_widget) "
        "SELECT w.id, o.id, layer, style, time_mode, time_widget "
        "FROM %(schema)s.layer_internal_wms AS w, %(schema)s.layer_ogc AS o where w.image_type=o.image_type AND o.type IS NOT NULL" % {
            'schema': schema,
        }
    )
    # internal with null image_type
    op.execute(
        "INSERT INTO %(schema)s.layer_wms (id, layer_ogc_id, layer, style, time_mode, time_widget) "
        "SELECT w.id, o.id, layer, style, time_mode, time_widget "
        "FROM %(schema)s.layer_internal_wms AS w, %(schema)s.layer_ogc AS o where w.image_type IS NULL AND o.image_type IS NULL" % {
            'schema': schema,
        }
    )

    op.drop_table('layer_external_wms', schema=schema)
    op.drop_table('layer_internal_wms', schema=schema)

    # update layer type in treeitems
    op.execute(
        "UPDATE %(schema)s.treeitem "
        "SET type='l_wms' "
        "WHERE type='l_int_wms' OR type='l_ext_wms'" % {
            'schema': schema,
        }
    )

def downgrade():
    schema = context.get_context().config.get_main_option('schema')

    # Instructions

    # recreate tables 'layer_internal_wms' and 'layer_external_wms'
    op.create_table(
        'layer_internal_wms',
        Column(
            'id', Integer, ForeignKey(schema + '.layer.id'), primary_key=True
        ),
        Column('layer', Unicode),
        Column('image_type', Unicode(10)),
        Column('style', Unicode),
        Column('time_mode', Unicode(8)),
        Column('time_widget', Unicode(10), default=u'slider'),
        schema=schema,
    )

    op.create_table(
        'layer_external_wms',
        Column(
            'id', Integer, ForeignKey(schema + '.layer.id'), primary_key=True
        ),
        Column('url', Unicode),
        Column('layer', Unicode),
        Column('image_type', Unicode(10)),
        Column('style', Unicode),
        Column('is_single_tile', Boolean),
        Column('time_mode', Unicode(8)),
        Column('time_widget', Unicode(10), default=u'slider'),
        schema=schema,
    )
    # move data back
    # external (type is null)
    op.execute(
        "INSERT INTO %(schema)s.layer_external_wms (id, url, layer, image_type, style, is_single_tile, time_mode, time_widget) "
        "SELECT w.id, url, layer, image_type, style, is_single_tile, time_mode, time_widget "
        "FROM %(schema)s.layer_wms AS w, %(schema)s.layer_ogc AS o "
        "WHERE w.layer_ogc_id=o.id AND o.type IS NULL" % {
            'schema': schema,
        }
    )
    # internal (type is not null)
    op.execute(
        "INSERT INTO %(schema)s.layer_internal_wms (id, layer, image_type, style, time_mode, time_widget) "
        "SELECT w.id, layer, image_type, style, time_mode, time_widget "
        "FROM %(schema)s.layer_wms AS w, %(schema)s.layer_ogc AS o WHERE w.layer_ogc_id=o.id AND o.type IS NOT NULL" % {
            'schema': schema,
        }
    )

    # drop table AFTER moving data back
    op.drop_table('layer_wms', schema=schema)
    op.drop_table('layer_ogc', schema=schema)

    # update layer type in treeitems
    # external
    op.execute(
        "UPDATE %(schema)s.treeitem "
        "SET type='l_ext_wms' "
        "FROM %(schema)s.layer_external_wms as w "
        "WHERE %(schema)s.treeitem.id=w.id" % {
            'schema': schema,
        }
    )
    # internal
    op.execute(
        "UPDATE %(schema)s.treeitem "
        "SET type='l_int_wms' "
        "FROM %(schema)s.layer_internal_wms as w "
        "WHERE %(schema)s.treeitem.id=w.id" % {
            'schema': schema,
        }
    )
