import logging
import copy

import simtk.openmm
import simtk.openmm.app
import simtk.unit as u

from openpathsampling.engines import DynamicsEngine, SnapshotDescriptor
from snapshot import Snapshot
import numpy as np

logger = logging.getLogger(__name__)


class OpenMMEngine(DynamicsEngine):
    """OpenMM dynamics engine based on 'simtk.openmm` system and integrator.

    The engine will create a :class:`simtk.openmm.app.Simulation` instance
    and uses this to generate new frames.

    """

    units = {
        'length': u.nanometers,
        'velocity': u.nanometers / u.picoseconds,
        'energy': u.joule / u.mole
    }

    _default_options = {
        'n_steps_per_frame': 10,
        'n_frames_max': 5000,
    }

    base_snapshot_type = Snapshot

    def __init__(
            self,
            topology,
            system,
            integrator,
            openmm_properties=None,
            options=None):
        """
        Parameters
        ----------
        topology : openpathsampling.engines.openmm.MDTopology
            a template snapshots which provides the topology object to be used
            to create the openmm engine
        system : simtk.openmm.app.System
            the openmm system object
        integrator : simtk.openmm.Integrator
            the openmm integrator object
        openmm_properties : dict
            optional setting for creating the openmm simuation object. Typical
            keys include GPU floating point precision
        options : dict
            a dictionary that provides additional settings for the OPS engine.
            Allowed are

                'n_steps_per_frame' : int, default: 10
                    the number of integration steps per returned snapshot
                'n_frames_max' : int or None, default: 5000,
                    the maximal number of frames allowed for a returned
                    trajectory object
                `platform` : str, default: `fastest`,
                    the openmm specification for the platform to be used,
                    also 'fastest' is allowed   which will pick the currently
                    fastest one available

        Notes
        -----
        the `n_frames_max` does not limit Trajectory objects in length. It only
        limits the maximal length of returned trajectory objects when this
        engine is used.
        """

        self.system = system
        self.integrator = integrator
        self.topology = topology

        dimensions = {
            'n_atoms': topology.n_atoms,
            'n_spatial': topology.n_spatial
        }

        descriptor = SnapshotDescriptor.construct(
            Snapshot,
            dimensions
        )

        super(OpenMMEngine, self).__init__(
            options=options,
            descriptor=descriptor
        )

        if openmm_properties is None:
            openmm_properties = {}

        self.openmm_properties = openmm_properties

        # set no cached snapshot
        self._current_snapshot = None
        self._current_momentum = None
        self._current_configuration = None
        self._current_box_vectors = None

        self._simulation = None

    def from_new_options(
            self,
            integrator=None,
            openmm_properties=None,
            options=None):
        """
        Create a new engine from existing, but different optionsor integrator

        Parameters
        ----------
        integrator : simtk.openmm.Integrator
            the openmm integrator object
        openmm_properties : dict
            optional setting for creating the openmm simuation object. Typical
            keys include GPU floating point precision
        options : dict
            a dictionary that provides additional settings for the OPS engine.
            Allowed are

                'n_steps_per_frame' : int, default: 10
                    the number of integration steps per returned snapshot
                'n_frames_max' : int or None, default: 5000,
                    the maximal number of frames allowed for a returned
                    trajectory object
                `platforms` : list of str,
                    the openmm specification for the platform to be used,
                    also 'fastest' is allowed which will pick the currently
                    fastest one available

        Notes
        -----
        This can be used to quickly set up simulations at various temperatures
        or change the step sizes.

        """
        if integrator is None:
            integrator = self.integrator

        new_options = dict()
        new_options.update(self.options)

        if options is not None:
            new_options.update(options)

        new_properties = False
        if openmm_properties is None:
            new_properties = True
            openmm_properties = self.openmm_properties

        new_engine = OpenMMEngine(
            self.topology,
            self.system,
            integrator,
            openmm_properties=openmm_properties,
            options=new_options)

        if self._simulation is not None and \
                integrator is self.integrator and \
                not new_properties:

            # apparently we use a simulation object which is the same as the
            # new one since we do not change the platform or
            # change the integrator it means if it exists we copy the
            # simulation object

            new_engine._simulation = self._simulation

        return new_engine

    @property
    def platform(self):
        """
        str : Return the name of the currently used platform

        """
        if self._simulation is not None:
            return self._simulation.context.getPlatform().getName()
        else:
            return None

    @property
    def simulation(self):
        if self._simulation is None:
            self.initialize()

        return self._simulation

    def reset(self):
        """
        Remove the simulation object and allow recreation.

        If you want to explicitely change the used platform, etc.

        """

        logger.info('Removed existing OpenMM engine.')
        self._simulation = None

    def initialize(self, platform=None):
        """
        Create the final OpenMMEngine

        Parameters
        ----------
        platform : str or `simtk.openmm.Platform`
            either a string with a name of the platform a platform object

        Notes
        -----
        This step is OpenMM specific and will actually create the openmm.
        Simulation object used to run the simulations. The object will be
        created automatically the first time the engine is used. This way we
        will not create unnecessay Engines in memory during analysis.

        """

        if self._simulation is None:
            if type(platform) is str:
                self._simulation = simtk.openmm.app.Simulation(
                    topology=self.topology.mdtraj.to_openmm(),
                    system=self.system,
                    integrator=self.integrator,
                    platform=simtk.openmm.Platform.getPlatformByName(platform),
                    platformProperties=self.openmm_properties
                )
            elif platform is None:
                self._simulation = simtk.openmm.app.Simulation(
                    topology=self.topology.mdtraj.to_openmm(),
                    system=self.system,
                    integrator=self.integrator,
                    platformProperties=self.openmm_properties
                )
            else:
                self._simulation = simtk.openmm.app.Simulation(
                    topology=self.topology.mdtraj.to_openmm(),
                    system=self.system,
                    integrator=self.integrator,
                    platform=platform,
                    platformProperties=self.openmm_properties
                )

            logger.info(
                'Initialized OpenMM engine using platform `%s`' %
                self.platform)

    @staticmethod
    def available_platforms():
        return [
            simtk.openmm.Platform.getPlatform(platform_idx).getName()
            for platform_idx in range(simtk.openmm.Platform.getNumPlatforms())
        ]

    def to_dict(self):
        system_xml = simtk.openmm.XmlSerializer.serialize(self.system)
        integrator_xml = simtk.openmm.XmlSerializer.serialize(self.integrator)

        return {
            'system_xml': system_xml,
            'integrator_xml': integrator_xml,
            'topology': self.topology,
            'options': self.options,
            'properties': self.openmm_properties
        }

    @classmethod
    def from_dict(cls, dct):
        system_xml = dct['system_xml']
        integrator_xml = dct['integrator_xml']
        topology = dct['topology']
        options = dct['options']
        properties = dct['properties']

        return OpenMMEngine(
            topology=topology,
            system=simtk.openmm.XmlSerializer.deserialize(system_xml),
            integrator=simtk.openmm.XmlSerializer.deserialize(integrator_xml),
            options=options,
            openmm_properties=properties
        )

    @property
    def snapshot_timestep(self):
        return self.n_steps_per_frame * self.simulation.integrator.getStepSize()

    # def strip_units(self, item):
        # """Remove units and report in the md_unit_system

        # Parameters
        # ----------
        # item : simtk.unit.Quantity or iterable of simtk.unit.Quantity
            # the input with units

        # Returns
        # -------
        # float or iterable
            # resulting value in the simtk.units.md_unit_system, but without
            # units attached
        # """
        # try:
            # # ideally, this works -- other choices are much slower
            # return item.value_in_unit_system(u.md_unit_system)
        # except AttributeError:
            # # if this fails, then we don't know what `item` was: not
            # # quantity, not iterable
            # iterator_length = len(item)

            # # we copy the item so that we ensure we get the same type
            # new_item = copy.copy(item)
            # for i in range(iterator_length):
                # new_item[i] = item[i].value_in_unit_system(u.md_unit_system)
            # return item


    def _build_current_snapshot(self):
        # TODO: Add caching for this and mark if changed

        state = self.simulation.context.getState(getPositions=True,
                                                 getVelocities=True,
                                                 getEnergy=True)

        snapshot = Snapshot.construct(
            coordinates=state.getPositions(asNumpy=True),
            box_vectors=state.getPeriodicBoxVectors(asNumpy=True),
            velocities=state.getVelocities(asNumpy=True),
            engine=self
        )

        return snapshot

    @staticmethod
    def is_valid_snapshot(snapshot):
        if np.isnan(np.min(snapshot.coordinates._value)):
            return False

        if np.isnan(np.min(snapshot.velocities._value)):
            return False

        return True

    @property
    def current_snapshot(self):
        if self._current_snapshot is None:
            self._current_snapshot = self._build_current_snapshot()

        return self._current_snapshot

    def _changed(self):
        self._current_snapshot = None

    @current_snapshot.setter
    def current_snapshot(self, snapshot):
        self.check_snapshot_type(snapshot)

        if snapshot is not self._current_snapshot:
            # if snapshot.coordinates is not None:
            self.simulation.context.setPositions(snapshot.coordinates)

            # if snapshot.box_vectors is not None:
            self.simulation.context.setPeriodicBoxVectors(
                snapshot.box_vectors[0],
                snapshot.box_vectors[1],
                snapshot.box_vectors[2]
            )

            # if snapshot.velocities is not None:
            self.simulation.context.setVelocities(snapshot.velocities)

            # After the updates cache the new snapshot
            if snapshot.engine is self:
                # no need for copy if this snap is from this engine
                self._current_snapshot = snapshot
            else:
                self._current_snapshot = self._build_current_snapshot()

    def generate_next_frame(self):
        self.simulation.step(self.n_steps_per_frame)
        self._current_snapshot = None
        return self.current_snapshot

    def minimize(self):
        self.simulation.minimizeEnergy()
        # make sure that we get the minimized structure on request
        self._current_snapshot = None
