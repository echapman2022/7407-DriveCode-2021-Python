from telnetlib import EL
import wpilib

from commands2 import InstantCommand, ParallelCommandGroup, ConditionalCommand, SequentialCommandGroup, WaitCommand
import commands2
from robotpy_toolkit_7407.command import SubsystemCommand, T
from robotpy_toolkit_7407.unum import Unum
from robotpy_toolkit_7407.unum.units import cm
from robotpy_toolkit_7407.motors.ctre_motors import talon_sensor_unit
from robotpy_toolkit_7407.utils.units import m, s, inch

import constants
from robot_systems import Robot
from subsystem import Elevator


def elevator_down():
    Robot.elevator.set_height(0 * inch)
    Robot.drivetrain.max_vel = constants.drivetrain_max_vel


ElevatorDown = lambda: InstantCommand(elevator_down, Robot.elevator)
ElevatorSolenoidExtend = lambda: InstantCommand(Robot.elevator.extend_solenoid, Robot.elevator)
ElevatorSolenoidRetract = lambda: InstantCommand(Robot.elevator.retract_solenoid, Robot.elevator)
ElevatorSolenoidToggle = lambda: InstantCommand(Robot.elevator.solenoid.toggle, Robot.elevator)

def restrict_robot_vel():
    Robot.drivetrain.max_vel = constants.drivetrain_max_climb_vel

ElevatorSetupCommand = lambda: ParallelCommandGroup(
    InstantCommand(lambda: restrict_robot_vel()),
    InstantCommand(lambda: Robot.elevator.set_height(constants.elevator_extended_height)),
    ElevatorSolenoidRetract()
)

# pull the robot onto the mid/high bar
class ElevatorClimbStep1(SubsystemCommand[Elevator]):
    def __init__(self, subsystem: T, tolerance: Unum = 0.5 * cm):
        super().__init__(subsystem)
        self.tolerance = tolerance
        self.grabbed = False
        self.aborted = False
        self.aborted2 = False
        self.setpoint = constants.elevator_pull_down_height

    def initialize(self) -> None:
        self.grabbed = False
        self.aborted = False
        self.aborted2 = False
        self.setpoint = constants.elevator_pull_down_height

    def execute(self) -> None:
        self.subsystem.set_height(self.setpoint)

        # after we miss the bar and re-extend elevator to the top, aborted part 2 start
        if self.aborted:
            if self.at_setpoint():
                self.aborted = False
                self.aborted2 = True
                self.setpoint = constants.elevator_extended_height
            return

        # double checking that elevator is re-extended to the top, and then ask it to pull down to the bar again
        if self.aborted2:
            if self.at_setpoint():
                self.aborted2 = False
                self.setpoint = constants.elevator_pull_down_height
            return

        # set grab status to true if limit switches on elevator hooks are pressed
        if self.subsystem.bar_on_climb_hooks():
            self.grabbed = True
            
        # if we're not grabbed onto the bar and the elevator went pass the bar height, and send the elevator all the way back up again
        if self.subsystem.get_height() <= constants.elevator_min_bar_contact_height:
            if not self.grabbed:
                self.aborted = True
                self.aborted2 = False
                self.setpoint = constants.elevator_extended_height

    # finish when the robot is pulled onto the bar and elevator not going up and down like crazy
    def isFinished(self) -> bool:
        return self.at_setpoint() and not (self.aborted or self.aborted2)
    
    # check if we're at the height we tell the elevator to be
    def at_setpoint(self) -> bool:
        return abs(self.subsystem.get_height() - self.setpoint) <= self.tolerance


# extend elevator so that t-rex hooks are holding onto mid/high bar
class ElevatorClimbStep2(SubsystemCommand[Elevator]):
    def __init__(self, subsystem: T, tolerance: Unum = 0.5 * cm):
        super().__init__(subsystem)
        self.tolerance = tolerance
        self.latched = False
        self.aborted = False
        self.setpoint = constants.elevator_latch_height

    def initialize(self) -> None:
        self.latched = False
        self.setpoint = constants.elevator_latch_height
        self.aborted = False
        
    def execute(self) -> None:
        self.subsystem.set_height(self.setpoint)

        if self.aborted:
            return

        # if limit switches on t-rex arms are triggered, set status to latched onto the next bar
        if self.subsystem.bar_on_grab_hooks() and not self.latched:
            self.latched = True

    # end the command if elevator not going up and down and t-rex hooks on next bar. 
    # start going down if we're not latched on and elevator is extended
    # start going back up if we ran the elevator
    def isFinished(self) -> bool:
        if self.at_setpoint():
            if not self.aborted:
                if not self.latched:
                    self.aborted = True
                    self.setpoint = constants.elevator_pull_down_height
                    return False 
                return True
            else:
                self.aborted = False
                self.setpoint = constants.elevator_latch_height
        return False
    
    def at_setpoint(self) -> bool:
        return abs(self.subsystem.get_height() - self.setpoint) <= self.tolerance


# (mid to high) extend pistons so the the robot tilt's backwards, also extend elevator towards next bar
class ElevatorClimbStep3(SubsystemCommand[Elevator]):
    def __init__(self, subsystem: T, tolerance: Unum = 0.5 * cm):
        super().__init__(subsystem)
        self.tolerance = tolerance
        self.fired = False

    def initialize(self) -> None:
        self.fired = False

    
    # pull the elevator back, and if we pull the elevator pass a certain stage, extend the pistons
    def execute(self) -> None:
        self.subsystem.set_height(constants.elevator_extended_height)
        if not self.fired and self.subsystem.get_height() >= constants.elevator_fire_height:
            self.fired = True
            self.subsystem.extend_solenoid()

    def isFinished(self) -> bool:
        return abs(self.subsystem.get_height() - constants.elevator_extended_height) <= self.tolerance
    
    
# (high to traverse) extend pistons so the the robot tilt's backwards, also extend elevator just below traversal bar
class ElevatorClimbStep4(SubsystemCommand[Elevator]):
    def __init__(self, subsystem: T, tolerance: Unum = 0.5 * cm):
        super().__init__(subsystem)
        self.tolerance = tolerance
        self.fired = False

    def initialize(self) -> None:
        self.fired = False

    
    # pull the elevator back, and if we pull the elevator pass a certain stage, extend the pistons
    def execute(self) -> None:
        self.subsystem.set_height(constants.elevator_below_extended_height)
        if not self.fired and self.subsystem.get_height() >= constants.elevator_fire_height:
            self.fired = True
            self.subsystem.extend_solenoid()

    def isFinished(self) -> bool:
        return abs(self.subsystem.get_height() - constants.elevator_below_extended_height) <= self.tolerance


# keep extending elevator towards traversal bar
class ElevatorClimbStep5(SubsystemCommand[Elevator]):
    def __init__(self, subsystem: T, tolerance: Unum = 0.5 * cm):
        super().__init__(subsystem)
        self.tolerance = tolerance

    def initialize(self) -> None:
        pass

    def execute(self) -> None:
        self.subsystem.set_height(constants.elevator_extended_height)

    def isFinished(self) -> bool:
        return abs(self.subsystem.get_height() - constants.elevator_extended_height) <= self.tolerance


# pull the elevator to the latch height onto traversal at the end, so we rest on t-rex hooks
class ElevatorClimbStep6(SubsystemCommand[Elevator]):
    def __init__(self, subsystem: T, tolerance: Unum = 0.5 * cm):
        super().__init__(subsystem)
        self.tolerance = tolerance

    def initialize(self) -> None:
        pass
    def execute(self) -> None:
        self.subsystem.set_height(constants.elevator_latch_height)

    def isFinished(self) -> bool:
        return abs(self.subsystem.get_height() - constants.elevator_latch_height) <= self.tolerance


def abort_fn():
    pass



ElevatorClimbCommand = lambda: SequentialCommandGroup(
    ElevatorClimbStep1(Robot.elevator),
    ElevatorClimbStep2(Robot.elevator),
    ElevatorClimbStep3(Robot.elevator),
    ElevatorSolenoidRetract().andThen(
        SequentialCommandGroup(
            WaitCommand(0.5),
            ElevatorClimbStep1(Robot.elevator),
            ElevatorClimbStep2(Robot.elevator),
            ElevatorClimbStep4(Robot.elevator),
            WaitCommand(0.25), 
            ElevatorClimbStep5(Robot.elevator),
            ElevatorSolenoidRetract().andThen(
                SequentialCommandGroup(
                    WaitCommand(1), # make this wait slightly shorter, possibly 0.5 / 0.75
                    ElevatorClimbStep1(Robot.elevator),
                    ElevatorClimbStep6(Robot.elevator)
                )
            )
        )
    )
)
