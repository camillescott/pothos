#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2024
# File   : ponderosa.py
# License: BSD 3-Clause
# Author : Camille Scott <camille@bogg.cc>
# Date   : 02.11.2024

from argparse import (Action,
                      ArgumentParser, 
                      _ArgumentGroup,
                      Namespace,
                      _SubParsersAction)
from collections import deque
from functools import wraps
from itertools import pairwise
from typing import Callable


Subparsers = _SubParsersAction
NamespaceFunc = Callable[[Namespace], int | None]
ArgParser = ArgumentParser | _ArgumentGroup
ArgAdderFunc = Callable[[ArgParser], Action | None]


class SubCmd:
    '''
    Represents a subcommand in the command tree.

    Args:
        parser (ArgumentParser): The argument parser for the subcommand.
        name (str): The name of the subcommand.
        cmd_tree (CmdTree): The command tree the subcommand belongs to.
    '''

    def __init__(self, parser: ArgumentParser,
                       name: str,
                       cmd_tree: 'CmdTree'):
        self.parser = parser
        self.name = name
        self.cmd_tree = cmd_tree

    def args(self, groupname: str | None = None,
                   desc: str | None = None,
                   common: bool = False):
        '''
        Registers arguments for the subcommand.

        Args:
            groupname (str | None, optional): Name of the argument group.
            desc (str | None, optional): Description of the argument group.
            common (bool, optional): If True, registers common arguments across subcommands.

        Returns:
            Callable: The argument wrapper function.
        '''
        
        def wrapper(arg_adder: ArgAdderFunc):
            print(f'SubCmd.args.wrapper: {self.name}')
            group = ArgGroup(groupname, arg_adder, desc=desc)
            apply_func = group.apply(common=common)
            apply_func(self)
            return group
        return wrapper

    @property
    def func(self):
        '''
        Gets the function associated with the subcommand.

        Returns:
            Callable: The function set via 'set_defaults' in ArgumentParser.
        '''
        return self.parser._defaults['func']

    @func.setter
    def func(self, new_func: NamespaceFunc):
        '''
        Sets the function associated with the subcommand.

        Args:
            new_func (NamespaceFunc): The function to set.
        '''
        self.parser._defaults['func'] = new_func


class CmdTree:
    '''
    Manages a tree of subparsers and facilitates registering functions
    for the subcommands.

    Args:
        root (ArgumentParser | None, optional): The root parser of the command tree.
        **kwargs: Additional arguments passed to the ArgumentParser.
    '''

    def __init__(self, root: ArgumentParser | None = None, **kwargs):
        '''
        Initializes the CmdTree with a root parser.
        '''
        if root is None:
            self._root = ArgumentParser(**kwargs)
        else:
            self._root = root
        self._root.set_defaults(func = lambda _: self._root.print_help())
        if not self._get_subparsers(self._root):
            self._root.add_subparsers()
        
        self.root = SubCmd(self._root, self._root.prog, self)
        self.common_adders: list[tuple[str | None, ArgAdderFunc]] = []

    def parse_args(self, *args, **kwargs):
        '''
        Parses command-line arguments.

        Args:
            *args: Variadic positional arguments for ArgumentParser.
            **kwargs: Variadic keyword arguments for ArgumentParser.

        Returns:
            Namespace: The collected argument Namespace.
        '''
        self._apply_common_args()
        return self._root.parse_args(*args, **kwargs)

    def run(self, args: Namespace | None = None) -> int:
        '''
        Parses the arguments and executes the registered functions.

        Args:
            args (Namespace | None): The parsed Namespace to execute. If None, args are parsed.

        Returns:
            int: The return code of executed function, 0 if None.
        '''
        if args is None:
            args = self.parse_args()
        if (retcode := args.func(args)) is None:
            return 0
        return retcode

    def _get_subparser_action(self, parser: ArgumentParser) -> _SubParsersAction | None:
        '''
        Extracts the subparser action from the provided parser.

        Args:
            parser (ArgumentParser): The argument parser to search.

        Returns:
            _SubParsersAction | None: The extracted subparser action, if found.
        '''
        for action in parser._actions:
            if isinstance(action, _SubParsersAction):
                return action
        return None

    def _get_subparsers(self, parser: ArgumentParser):
        '''
        Retrieves subparsers for the provided parser.

        Args:
            parser (ArgumentParser): The parser for which subparsers are retrieved.

        Yields:
            Tuple: Name and argument parser for each subparser.
        '''
        action = self._get_subparser_action(parser)
        if action is not None:
            yield from action.choices.items()

    def _find_cmd(self, cmd_name: str, root: ArgumentParser | None = None) -> ArgumentParser | None:
        '''
        Finds a subcommand by its name, performing a breadth-first search.

        Args:
            cmd_name (str): The name of the subcommand to find.
            root (ArgumentParser | None, optional): The parser to start at. Defaults to root parser.

        Returns:
            ArgumentParser | None: The subcommand parser, or None if not found.
        '''
        if root is None:
            root = self._root
        
        if cmd_name == root.prog:
            return root

        subparser_deque = deque(self._get_subparsers(root))
        while subparser_deque:
            root_name, root_parser = subparser_deque.popleft()
            if root_name == cmd_name:
                return root_parser
            else:
                subparser_deque.extend(self._get_subparsers(root_parser))
        return None

    def gather_subtree(self, root_name: str | None) -> list[ArgumentParser]:
        '''
        Gathers all subparsers starting from the provided root name.

        Args:
            root_name (str | None): The root subparser name to start gathering from.

        Returns:
            list[ArgumentParser]: List of the collected argument parsers in the subtree.
        '''
        if root_name is None:
            root = self._root
        else:
            root = self._find_cmd(root_name)
        if root is None:
            return []
        found : list[ArgumentParser] = [root]
        parser_q = deque(self._get_subparsers(root))
        while parser_q:
            _, root = parser_q.popleft()
            parser_q.extend(self._get_subparsers(root))
            found.append(root)
        return found

    def _find_cmd_chain(self, cmd_fullname: list[str]) -> list[ArgumentParser | None]:
        '''
        Finds a command chain of subcommands from a fullname list.

        Args:
            cmd_fullname (list[str]): List representing the command chain.

        Returns:
            list[ArgumentParser | None]: List of argument parsers corresponding to the chain.
        '''
        root_name = cmd_fullname[0]
        if (root_parser := self._find_cmd(root_name)) is None:
            return [None] * len(cmd_fullname)
        elif len(cmd_fullname) == 1:
            return [root_parser]
        else:
            chain : list[ArgumentParser | None] = [root_parser]
            for next_name in cmd_fullname[1:]:
                found = False
                for child_name, child_parser in self._get_subparsers(root_parser):
                    if child_name == next_name:
                        root_parser = child_parser
                        chain.append(child_parser)
                        found = True
                        break
                if not found:
                    break
            if len(chain) != len(cmd_fullname):
                chain.extend([None] * (len(cmd_fullname) - len(chain)))
            return chain

    def _add_child(self, root: ArgumentParser,
                         child_name: str,
                         func = None,
                         aliases: list[str] | None = None,
                         help: str | None = None):
        '''
        Adds a child subparser to the root parser.

        Args:
            root (ArgumentParser): The root parser.
            child_name (str): The name for the child subparser.
            func (Callable, optional): The function to associate with the child subcommand.
            aliases (list[str] | None, optional): Aliases for the child subcommand.
            help (str | None, optional): Help text for the child subcommand.

        Returns:
            ArgumentParser: The added child subparser.
        '''
        if (subaction := self._get_subparser_action(root)) is None:
            subaction = root.add_subparsers()
        child = subaction.add_parser(child_name, help=help, aliases=aliases if aliases else [])
        cmd_func = (lambda _: child.print_help()) if func is None else func
        child.set_defaults(func=cmd_func)
        return child

    def register_cmd(self, cmd_fullname: list[str],
                           cmd_func: NamespaceFunc,
                           aliases: list[str] | None = None,
                           help: str | None = None):
        '''
        Registers a fully qualified command name with a function.

        Args:
            cmd_fullname (list[str]): The full name of the command.
            cmd_func (NamespaceFunc[P]): The function associated with the command.
            aliases (list[str] | None, optional): Aliases of the subcommand.
            help (str | None, optional): Help text for the subcommand.

        Returns:
            ArgumentParser: The registered subcommand parser.
        '''
        chain = self._find_cmd_chain(cmd_fullname)
        if not any(map(lambda el: el is None, chain)):
            raise ValueError(f'subcommand {cmd_fullname} already registered')
        if chain[0] is None:
            chain = [self._root] + chain
            cmd_fullname = [self._root.prog] + cmd_fullname
        leaf_name = cmd_fullname[-1]
        for i, j in pairwise(range(len(chain))):
            if chain[j] is None:
                if chain[i] is None:
                    raise ValueError(f'Bad argument chain: {chain[i]}->{chain[j]}')
                elif cmd_fullname[j] == leaf_name:
                    return self._add_child(chain[i], leaf_name, func=cmd_func, aliases=aliases, help=help)
                else:
                    child = self._add_child(chain[i], cmd_fullname[j])
                    chain[j] = child
        raise ValueError(f'{leaf_name} was not registered')

    def register(self, *cmd_fullname: str,
                       aliases: list[str] | None = None,
                       help: str | None = None):
        '''
        Registers a new subcommand with the CmdTree.

        Args:
            *cmd_fullname (str): Variable-length subcommand name string.
            aliases (list[str] | None, optional): Aliases of the subcommand.
            help (str | None, optional): Help text for the subcommand.

        Returns:
            Callable: The subcommand wrapper.
        '''
        def wrapper(cmd_func: NamespaceFunc):
            return SubCmd(self.register_cmd(list(cmd_fullname),
                                            cmd_func,
                                            aliases=aliases,
                                            help=help),
                          cmd_fullname[-1],
                          self)
        return wrapper

    def register_common_args(self, cmd_root: str | None, arg_adder: ArgAdderFunc):
        '''
        Registers common arguments across multiple subcommands.

        Args:
            cmd_root (str | None): The root command to apply common arguments.
            arg_adder (ArgAdderFunc): Function that adds arguments.
        '''
        self.common_adders.append((cmd_root, arg_adder))

    def _apply_common_args(self):
        '''
        Applies the registered common arguments to their respective parsers.
        '''
        for root_name, arg_adder in self.common_adders:
            for parser in self.gather_subtree(root_name):
                arg_adder(parser)

    def _get_help(self, parser, cmds: list[str], name: str | None = None, level: int = 0):
        '''
        Recursively gathers help information from a parser and its subparsers.

        Args:
            parser (ArgumentParser): The parser to get help from.
            cmds (list[str]): List to append help information to.
            name (str | None, optional): Name of the parser. Defaults to None.
            level (int, optional): Indentation level for subcommands.
        '''
        indent = '  ' * level
        if name is None:
            name = parser.prog
        args = []
        for action in parser._actions:
            if isinstance(action, _SubParsersAction):
                for subparser_action, (subparser_name, subparser) in zip(action._get_subactions(), action.choices.items()):
                    help = subparser_action.help or ''
                    cmds.append(f'{indent}  {subparser_action.dest}: {help}')
                    self._get_help(subparser, cmds, name=subparser_name, level=level+1)  # Recursively traverse subparsers
            else:
                args.append(action.dest)
                
    def print_help(self):
        '''
        Prints the help information for the entire command tree.
        '''
        cmds = [self._root.format_usage(),
                'Subcommands:']
        self._get_help(self._root, cmds, self._root.prog)
        print('\n'.join(cmds))


def postprocess_args(func: NamespaceFunc,
                     postprocessors: list[NamespaceFunc]):
    '''
    Wraps a function with postprocessors.

    Args:
        func (NamespaceFunc): The main function for subcommand arguments.
        postprocessors (list[NamespaceFunc]): List of postprocessor functions.

    Returns:
        NamespaceFunc: The wrapped function with postprocessing logic.
    '''
    @wraps(func)
    def wrapper(args: Namespace):
        for postproc_func in postprocessors:
            postproc_func(args)
        func(args)
    return wrapper


class ArgGroup:
    '''
    Represents a group of arguments for an argument parser or subcommand.

    Args:
        group_name (str | None): The name of the argument group.
        arg_func (ArgAdderFunc): The function that adds arguments to the group.
        desc (str | None, optional): Description of the argument group.
    '''

    def __init__(self, group_name: str | None,
                       arg_func: ArgAdderFunc,
                       desc: str | None = None):
        self.group_name = group_name
        self.arg_func = arg_func
        self.desc = desc
        self.postprocessors: list[Callable[[Namespace], None]] = []

    def apply(self, common: bool = False, *args, **kwargs):
        '''
        Applies the argument group to a parser.

        Args:
            common (bool, optional): If True, registers the argument group as a common group.
            *args: Additional arguments passed to the argument adder function.
            **kwargs: Additional keyword arguments passed to the argument adder function.

        Returns:
            Callable: The apply wrapper function.
        '''
        def _apply_group(parser: ArgumentParser):
            if self.group_name is None:
                group = parser
            else:
                group = parser.add_argument_group(title=self.group_name,
                                                  description=self.desc)
            self.arg_func(group, *args, **kwargs)
            parser.set_defaults(func=postprocess_args(parser.get_default('func'),
                                                      self.postprocessors))
        def wrapper(target: SubCmd):
            if common:
                target.cmd_tree.register_common_args(target.name, _apply_group)
            else:
                _apply_group(target.parser)
            return target
        return wrapper

    def postprocessor(self, func: Callable[[Namespace], None]):
        '''
        Adds a postprocessor function to the argument group.

        Args:
            func (Callable[[Namespace], None]): The postprocessor function to add.

        Returns:
            Callable: The input function itself.
        '''
        self.postprocessors.append(func)
        return func


def arggroup(groupname: str | None = None,
             desc: str | None = None):
    def wrapper(adder_func: ArgAdderFunc):
        return ArgGroup(groupname, adder_func, desc=desc)
    return wrapper