""" Mixin proxy for risk jobs, and associated
Risk Job Mixin decorators """

import json
import os

from openquake.output import geotiff
from openquake import job
from openquake.job import mixins
from openquake import kvs 
from openquake import logs
from openquake import risk
from openquake import shapes
from openquake.output import risk as risk_output

from celery.decorators import task

LOG = logs.LOG

def output(fn):
    """ Decorator for output """
    def output_writer(self, *args, **kwargs):
        """ Write the output of a block to memcached. """
        fn(self, *args, **kwargs)
        conditional_loss_poes = [float(x) for x in self.params.get(
                    'CONDITIONAL_LOSS_POE', "0.01").split()]
        #if result:
        results = []
        for block_id in self.blocks_keys:
            results.extend(self._write_output_for_block(self.job_id, block_id))
        for loss_poe in conditional_loss_poes:
            results.extend(self.write_loss_map(loss_poe))
        return results

    return output_writer


@task
def compute_risk(job_id, block_id, **kwargs):
    engine = job.Job.from_kvs(job_id)
    with mixins.Mixin(engine, RiskJobMixin, key="risk") as mixed:
        mixed.compute_risk(block_id, **kwargs)
        

class RiskJobMixin(mixins.Mixin):
    """ A mixin proxy for Risk jobs """
    mixins = {}
    
    def _write_output_for_block(self, job_id, block_id):
        decoder = json.JSONDecoder()
        loss_ratio_curves = []
        block = job.Block.from_kvs(block_id)
        for point in block.grid(self.region):
            asset_key = risk.asset_key(self.id, point.row, point.column)
            asset_list = kvs.get_client().lrange(asset_key, 0, -1)
            for asset in [decoder.decode(x) for x in asset_list]:
                site = shapes.Site(asset['lon'], asset['lat'])
                key = risk.loss_ratio_key(
                        job_id, point.row, point.column, asset["AssetID"])
                loss_ratio_curve = kvs.get(key)
                if loss_ratio_curve:
                    loss_ratio_curve = shapes.Curve.from_json(loss_ratio_curve)
                    loss_ratio_curves.append((site, loss_ratio_curve))

        LOG.debug("Serializing loss_ratio_curves")
        filename = "%s-block-%s.xml" % (
            self['LOSS_CURVES_OUTPUT_PREFIX'], block_id)
        path = os.path.join(self.base_path, self['OUTPUT_DIR'], filename)
        output_generator = risk_output.LossRatioCurveXMLWriter(path)
        output_generator.serialize(loss_ratio_curves)
        return [path]
    
    def write_loss_map(self, loss_poe):
        """ Iterates through all the assets and maps losses at loss_poe """
        decoder = json.JSONDecoder()
        # Make a special grid at a higher resolution
        risk_grid = shapes.Grid(self.region, float(self['RISK_CELL_SIZE']))
        filename = "%s-losses_at-%s.tiff" % (
            self.id, loss_poe)
        path = os.path.join(self.base_path, self['OUTPUT_DIR'], filename) 
        output_generator = geotiff.GeoTiffFile(path, risk_grid, 
                init_value=0.0, normalize=True)
        for point in self.region.grid:
            asset_key = risk.asset_key(self.id, point.row, point.column)
            asset_list = kvs.get_client().lrange(asset_key, 0, -1)
            for asset in [decoder.decode(x) for x in asset_list]:
                key = risk.loss_key(self.id, point.row, point.column, 
                        asset["AssetID"], loss_poe)
                loss = kvs.get(key)
                LOG.debug("Loss for asset %s at %s %s is %s" % 
                    (asset["AssetID"], asset['lon'], asset['lat'], loss))
                if loss:
                    loss_ratio = float(loss) / float(asset["AssetValue"])
                    risk_site = shapes.Site(asset['lon'], asset['lat'])
                    risk_point = risk_grid.point_at(risk_site)
                    output_generator.write(
                            (risk_point.row, risk_point.column), loss_ratio)
        output_generator.close()
        return [path]


mixins.Mixin.register("Risk", RiskJobMixin, order=2)